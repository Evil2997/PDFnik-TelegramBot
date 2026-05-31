# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/vtt_message.py
# repo: PDFnik-TelegramBot

import pathlib
import re
import uuid
from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.types import Audio, Document, Message, Video, Voice
from faststream.rabbit import RabbitBroker
from faststream.redis import Redis

from main_app.application.bot.vtt_contracts import (
    DeliveryMode,
    SourceType,
    TargetKind,
    TxtDelivery,
    TxtReply,
    TxtTarget,
    TxtTranscribeRequest,
)
from main_app.core.logger import logger
from main_app.infrastructure.storage import LocalFileStorage

_MIME_DEFAULT_EXT: dict[str, str] = {
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
    "video/webm": ".webm",
}

_YOUTUBE_URL_RE = re.compile(
    r"(?P<url>"
    r"(?:https?://)?"
    r"(?:(?:www|m)\.)?"
    r"(?:youtube\.com/(?:watch\?(?:[^ \n\r\t]*&)?v=[^ \n\r\t&]+(?:[^ \n\r\t]*)?|shorts/[^ \n\r\t/?&]+(?:\?[^ \n\r\t]*)?)"
    r"|youtu\.be/[^ \n\r\t/?&]+(?:\?[^ \n\r\t]*)?)"
    r")",
    re.IGNORECASE,
)

_VTT_DEDUP_TTL_SEC = 300


def _safe_suffix(filename: str) -> str:
    suffix = pathlib.Path(filename).suffix
    return suffix if suffix else ""


def _infer_upload_meta(msg: Message) -> tuple[SourceType, str, str]:
    if msg.voice:
        voice: Voice = msg.voice
        mime_type = voice.mime_type or "audio/ogg"
        extension = _MIME_DEFAULT_EXT.get(mime_type, ".ogg")
        filename = f"{voice.file_unique_id}{extension}"
        return "voice", filename, mime_type

    if msg.audio:
        audio: Audio = msg.audio
        mime_type = audio.mime_type or "audio/mpeg"
        filename = (
            audio.file_name or f"{audio.file_unique_id}{_MIME_DEFAULT_EXT.get(mime_type, '.mp3')}"
        )
        if not _safe_suffix(filename):
            filename = f"{filename}{_MIME_DEFAULT_EXT.get(mime_type, '.mp3')}"
        return "audio", filename, mime_type

    if msg.video:
        video: Video = msg.video
        mime_type = video.mime_type or "video/mp4"
        filename = (
            video.file_name or f"{video.file_unique_id}{_MIME_DEFAULT_EXT.get(mime_type, '.mp4')}"
        )
        if not _safe_suffix(filename):
            filename = f"{filename}{_MIME_DEFAULT_EXT.get(mime_type, '.mp4')}"
        return "video", filename, mime_type

    if msg.document:
        document: Document = msg.document
        mime_type = document.mime_type or "application/octet-stream"
        source_type: SourceType = "audio" if mime_type.lower().startswith("audio/") else "video"
        filename = (
            document.file_name or f"{document.file_unique_id}{_MIME_DEFAULT_EXT.get(mime_type, '')}"
        )
        if not _safe_suffix(filename):
            filename = f"{filename}{_MIME_DEFAULT_EXT.get(mime_type, '.bin')}"
        return source_type, filename, mime_type

    return "audio", "file.bin", "application/octet-stream"


def _resolve_delivery_mode(source_type: str) -> DeliveryMode:
    return "text" if source_type == "voice" else "document"


async def _download_media_bytes(bot: Bot, msg: Message) -> bytes:
    buffer = BytesIO()
    file_obj = msg.voice or msg.audio or msg.video or msg.document
    assert file_obj is not None
    await bot.download(file_obj, destination=buffer)
    return buffer.getvalue()


def _is_supported_document(msg: Message) -> bool:
    if not msg.document:
        return False
    mime_type = (msg.document.mime_type or "").lower()
    return mime_type.startswith("audio/") or mime_type.startswith("video/")


def _normalize_url(url: str) -> str:
    normalized = url.strip().rstrip(".,);]")
    if not normalized.lower().startswith("http"):
        normalized = "https://" + normalized
    return normalized


def _extract_first_youtube_url(text: str) -> str | None:
    match = _YOUTUBE_URL_RE.search(text or "")
    if not match:
        return None
    return _normalize_url(match.group("url"))


def _build_dedupe_key(chat_id: int, message_id: int) -> str:
    return f"vtt:dedupe:{chat_id}:{message_id}"


async def _acquire_dedupe_lock(redis: Redis, chat_id: int, message_id: int) -> bool:
    key = _build_dedupe_key(chat_id, message_id)
    try:
        result = await redis.set(key, "1", ex=_VTT_DEDUP_TTL_SEC, nx=True)
        return bool(result)
    except Exception as exc:
        logger.exception(
            "VTT dedupe check failed: chat_id=%s message_id=%s err=%s",
            chat_id,
            message_id,
            exc,
        )
        return True


def register_vtt_message_handlers(
    dp: Dispatcher,
    bot: Bot,
    storage: LocalFileStorage,
    broker: RabbitBroker,
    redis: Redis,
) -> None:
    async def _publish_job(
        *,
        job_id: str,
        target_kind: TargetKind,
        target_value: str,
        chat_id: int,
        reply_to_message_id: int | None,
        source_type: SourceType,
    ) -> bool:
        payload = TxtTranscribeRequest(
            job_id=job_id,
            target=TxtTarget(kind=target_kind, value=target_value),
            reply=TxtReply(chat_id=chat_id, reply_to_message_id=reply_to_message_id),
            delivery=TxtDelivery(
                source_type=source_type,
                mode=_resolve_delivery_mode(source_type),
            ),
            cfg={},
        )

        try:
            await broker.publish(payload.model_dump(exclude_none=True), queue="txt.transcribe")
            logger.info(
                "event=vtt_publish_ok job_id=%s chat_id=%s source_type=%s "
                "target_kind=%s target_value=%s delivery_mode=%s",
                job_id,
                chat_id,
                source_type,
                target_kind,
                target_value,
                payload.delivery.mode,
            )
            return True
        except Exception as exc:
            logger.exception(
                "event=vtt_publish_failed job_id=%s chat_id=%s source_type=%s "
                "target_kind=%s delivery_mode=%s err=%s",
                job_id,
                chat_id,
                source_type,
                target_kind,
                payload.delivery.mode,
                exc,
            )
            return False

    async def _handle_upload(msg: Message) -> None:
        chat_id = msg.chat.id
        reply_to_message_id = msg.message_id

        is_new_message = await _acquire_dedupe_lock(redis, chat_id, reply_to_message_id)
        if not is_new_message:
            logger.info(
                "event=vtt_duplicate_ignored chat_id=%s message_id=%s "
                "source_type=upload target_kind=storage_key",
                chat_id,
                reply_to_message_id,
            )
            return

        source_type, filename, mime_type = _infer_upload_meta(msg)
        job_id = str(uuid.uuid4())

        try:
            file_bytes = await _download_media_bytes(bot, msg)
        except Exception as exc:
            logger.exception(
                "event=vtt_download_failed job_id=%s chat_id=%s "
                "source_type=%s target_kind=storage_key err=%s",
                job_id,
                chat_id,
                source_type,
                exc,
            )
            await msg.answer("Could not download file from Telegram. Please try again.")
            return

        try:
            stored = await storage.save_bytes(
                file_bytes,
                prefix="uploads",
                filename=filename,
                content_type=mime_type or "application/octet-stream",
            )
        except Exception as exc:
            logger.exception(
                "event=vtt_storage_save_failed job_id=%s chat_id=%s "
                "source_type=%s target_kind=storage_key err=%s",
                job_id,
                chat_id,
                source_type,
                exc,
            )
            await msg.answer("Could not save file. Please try again.")
            return

        is_published = await _publish_job(
            job_id=job_id,
            target_kind="storage_key",
            target_value=stored.storage_key,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            source_type=source_type,
        )
        if not is_published:
            await msg.answer(
                "Could not submit transcription job. Please try later.\n" f"job_id: {job_id}"
            )
            return

        await msg.answer("Got it, transcribing...")

    async def _handle_youtube_link(msg: Message, url: str) -> None:
        chat_id = msg.chat.id
        reply_to_message_id = msg.message_id

        is_new_message = await _acquire_dedupe_lock(redis, chat_id, reply_to_message_id)
        if not is_new_message:
            logger.info(
                "event=vtt_duplicate_ignored chat_id=%s message_id=%s "
                "source_type=youtube target_kind=url",
                chat_id,
                reply_to_message_id,
            )
            return

        job_id = str(uuid.uuid4())

        is_published = await _publish_job(
            job_id=job_id,
            target_kind="url",
            target_value=url,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            source_type="youtube",
        )
        if not is_published:
            await msg.answer(
                "Could not submit YouTube for transcription. Please try later.\n"
                f"job_id: {job_id}"
            )
            return

        await msg.answer("Got it, transcribing...")

    @dp.message(F.text.regexp(_YOUTUBE_URL_RE))
    async def on_text_youtube(msg: Message) -> None:
        if not msg.text:
            return
        youtube_url = _extract_first_youtube_url(msg.text)
        if not youtube_url:
            return
        await _handle_youtube_link(msg, youtube_url)

    @dp.message(F.voice)
    async def on_voice(msg: Message) -> None:
        await _handle_upload(msg)

    @dp.message(F.audio)
    async def on_audio(msg: Message) -> None:
        await _handle_upload(msg)

    @dp.message(F.video)
    async def on_video(msg: Message) -> None:
        await _handle_upload(msg)

    @dp.message(F.document)
    async def on_document(msg: Message) -> None:
        if not _is_supported_document(msg):
            await msg.answer(
                "This document does not look like audio/video. Please send a voice/audio/video file 🙂"
            )
            return
        await _handle_upload(msg)
