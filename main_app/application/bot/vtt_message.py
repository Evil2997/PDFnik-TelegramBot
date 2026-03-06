from __future__ import annotations

import pathlib
import re
import uuid
from io import BytesIO
from typing import Optional, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.types import Audio, Document, Message, Video, Voice
from faststream.rabbit import RabbitBroker

from main_app.core.logger import logger
from main_app.infrastructure.storage import LocalFileStorage
from .vtt_contracts import SourceType, TxtTranscribeRequest


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

_YOUTUBE_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]+([&?][^\s]+)?",
    re.IGNORECASE,
)


def _safe_suffix(filename: str) -> str:
    suf = pathlib.Path(filename).suffix
    return suf if suf else ""


def _infer_source_type_and_meta(msg: Message) -> Tuple[SourceType, str, Optional[str]]:
    """
    Returns: (source_type, filename, mime_type)
    filename must have extension.
    """
    # VOICE
    if msg.voice:
        v: Voice = msg.voice
        mime = v.mime_type or "audio/ogg"
        ext = _MIME_DEFAULT_EXT.get(mime, ".ogg")
        filename = f"{v.file_unique_id}{ext}"
        return "voice", filename, mime

    # AUDIO
    if msg.audio:
        a: Audio = msg.audio
        mime = a.mime_type or "audio/mpeg"
        filename = a.file_name or f"{a.file_unique_id}{_MIME_DEFAULT_EXT.get(mime, '.mp3')}"
        if not _safe_suffix(filename):
            filename = f"{filename}{_MIME_DEFAULT_EXT.get(mime, '.mp3')}"
        return "audio", filename, mime

    # VIDEO
    if msg.video:
        v: Video = msg.video
        mime = v.mime_type or "video/mp4"
        filename = v.file_name or f"{v.file_unique_id}{_MIME_DEFAULT_EXT.get(mime, '.mp4')}"
        if not _safe_suffix(filename):
            filename = f"{filename}{_MIME_DEFAULT_EXT.get(mime, '.mp4')}"
        return "video", filename, mime

    # DOCUMENT (audio/video only)
    if msg.document:
        d: Document = msg.document
        mime = d.mime_type or "application/octet-stream"
        # decide whether it's audio or video
        st: SourceType = "audio" if mime.lower().startswith("audio/") else "video"
        filename = d.file_name or f"{d.file_unique_id}{_MIME_DEFAULT_EXT.get(mime, '')}"
        if not _safe_suffix(filename):
            ext = _MIME_DEFAULT_EXT.get(mime, ".bin")
            filename = f"{filename}{ext}"
        return st, filename, mime

    # fallback (should not happen)
    return "audio", "file.bin", "application/octet-stream"


async def _download_media_bytes(bot: Bot, msg: Message) -> bytes:
    buf = BytesIO()
    await bot.download(msg.voice or msg.audio or msg.video or msg.document, destination=buf)
    return buf.getvalue()


def _is_supported_document(msg: Message) -> bool:
    if not msg.document:
        return False
    mime = (msg.document.mime_type or "").lower()
    return mime.startswith("audio/") or mime.startswith("video/")


def _extract_first_youtube_url(text: str) -> Optional[str]:
    m = _YOUTUBE_RE.search(text or "")
    if not m:
        return None
    url = m.group(0)
    if not url.lower().startswith("http"):
        url = "https://" + url
    return url


def register_vtt_message_handlers(
    dp: Dispatcher,
    bot: Bot,
    storage: LocalFileStorage,
    broker: RabbitBroker,
) -> None:
    """
    Ingress:
      - voice/audio/video/document(audio|video)
      - YouTube link (text message containing youtube.com/youtu.be)
      - publish -> txt.transcribe
      - ACK immediately
    """

    async def _publish_job(
        *,
        job_id: str,
        chat_id: int,
        reply_to_message_id: Optional[int],
        source_type: SourceType,
        filename: str,
        mime_type: Optional[str],
        storage_key: Optional[str] = None,
        input_url: Optional[str] = None,
    ) -> bool:
        req = TxtTranscribeRequest(
            job_id=job_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            source_type=source_type,
            storage_key=storage_key,
            input_url=input_url,
            filename=filename,
            mime_type=mime_type,
            language=None,
            cfg=None,
        )
        try:
            await broker.publish(req.model_dump(), queue="txt.transcribe")
            logger.info(
                "VTT publish ok: chat_id=%s job_id=%s source_type=%s storage_key=%s input_url=%s",
                chat_id,
                job_id,
                source_type,
                storage_key,
                input_url,
            )
            return True
        except Exception as e:
            logger.exception(
                "VTT publish failed: chat_id=%s job_id=%s source_type=%s err=%s",
                chat_id,
                job_id,
                source_type,
                e,
            )
            return False

    async def _handle_upload(msg: Message) -> None:
        chat_id = msg.chat.id
        reply_to_message_id = msg.message_id

        source_type, filename, mime_type = _infer_source_type_and_meta(msg)
        job_id = str(uuid.uuid4())

        try:
            data = await _download_media_bytes(bot, msg)
        except Exception as e:
            logger.exception(
                "Failed to download media: chat_id=%s job_id=%s source_type=%s err=%s",
                chat_id,
                job_id,
                source_type,
                e,
            )
            await msg.answer("Не смог скачать файл из Telegram. Попробуйте ещё раз.")
            return

        try:
            stored = await storage.save_bytes(
                data,
                prefix="uploads",
                filename=filename,
                content_type=mime_type or "application/octet-stream",
            )
        except Exception as e:
            logger.exception(
                "Failed to save media: chat_id=%s job_id=%s source_type=%s err=%s",
                chat_id,
                job_id,
                source_type,
                e,
            )
            await msg.answer("Не смог сохранить файл. Попробуйте ещё раз.")
            return

        ok = await _publish_job(
            job_id=job_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            source_type=source_type,
            filename=stored.filename,
            mime_type=mime_type,
            storage_key=stored.storage_key,
            input_url=None,
        )
        if not ok:
            await msg.answer(
                "Не смог отправить задачу на расшифровку. Попробуйте позже.\n"
                f"job_id: {job_id}"
            )
            return

        await msg.answer("Принял, расшифровываю…")

    async def _handle_youtube_link(msg: Message, url: str) -> None:
        chat_id = msg.chat.id
        reply_to_message_id = msg.message_id
        job_id = str(uuid.uuid4())

        # минимальный контракт: отправляем input_url воркеру
        ok = await _publish_job(
            job_id=job_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            source_type="youtube",
            filename=f"youtube_{job_id}.mp4",  # воркеру может быть полезно иметь "имя"
            mime_type=None,
            storage_key=None,
            input_url=url,
        )
        if not ok:
            await msg.answer(
                "YouTube сейчас недоступен (не смог отправить задачу).\n"
                f"job_id: {job_id}"
            )
            return

        await msg.answer("Принял, расшифровываю…")

    # YouTube link ingress (must be registered before general text handler)
    @dp.message(F.text)
    async def on_text_youtube(msg: Message) -> None:
        if not msg.text:
            return
        url = _extract_first_youtube_url(msg.text)
        if not url:
            return  # allow other text handlers to process
        await _handle_youtube_link(msg, url)

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
            await msg.answer("Этот документ не похож на аудио/видео. Пришлите voice/audio/video 🙂")
            return
        await _handle_upload(msg)