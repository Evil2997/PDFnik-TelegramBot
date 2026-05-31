# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/txt_consumer.py
# repo: PDFnik-TelegramBot

from aiogram import Bot
from aiogram.types import BufferedInputFile
from faststream.rabbit import RabbitBroker

from main_app.application.bot.vtt_contracts import (
    TxtDoneError,
    TxtDoneSuccess,
    parse_txt_done_message,
)
from main_app.core.logger import logger
from main_app.domain.youtube_pdf_builder import build_youtube_pdf_order
from main_app.infrastructure.storage import LocalFileStorage

_TELEGRAM_TEXT_LIMIT = 4096
_SHORT_TEXT_LIMIT = 3800
_VOICE_MAX_TEXT_CHUNKS = 10
_DOCUMENT_CAPTION = "Transcript ready. Sending as file."


def _reply_kwargs(reply_to_message_id: int | None) -> dict:
    if reply_to_message_id:
        return {"reply_to_message_id": reply_to_message_id}
    return {}


def _chunk_text(text: str, chunk_size: int = _SHORT_TEXT_LIMIT) -> list[str]:
    if not text:
        return [""]
    safe_chunk_size = min(chunk_size, _TELEGRAM_TEXT_LIMIT - 50)
    chunks: list[str] = []
    for index in range(0, len(text), safe_chunk_size):
        chunks.append(text[index : index + safe_chunk_size])
    return chunks or [""]


def _target_kind_from_source_type(source_type: str | None) -> str:
    if source_type == "youtube":
        return "url"
    return "storage_key"


def _should_send_as_short_message(source_type: str, transcript_text: str) -> bool:
    if source_type in {"youtube", "video", "audio"}:
        return len(transcript_text) <= _SHORT_TEXT_LIMIT
    return False


async def _send_transcript_document(
    *,
    bot: Bot,
    chat_id: int,
    reply_to_message_id: int | None,
    txt_bytes: bytes,
    job_id: str,
    source_type: str,
    target_kind: str,
    caption: str | None = None,
) -> bool:
    filename = f"transcript_{job_id}.txt"
    try:
        file = BufferedInputFile(txt_bytes, filename)
        await bot.send_document(
            chat_id,
            file,
            caption=caption,
            **_reply_kwargs(reply_to_message_id),
        )
        logger.info(
            "event=vtt_send_result_ok job_id=%s chat_id=%s source_type=%s "
            "target_kind=%s delivery=document",
            job_id,
            chat_id,
            source_type,
            target_kind,
        )
        return True
    except Exception as exc:
        logger.exception(
            "event=vtt_send_result_failed job_id=%s chat_id=%s source_type=%s "
            "target_kind=%s delivery=document err=%s",
            job_id,
            chat_id,
            source_type,
            target_kind,
            exc,
        )
        await bot.send_message(
            chat_id,
            f"Transcript is ready but could not send the file.\njob_id: {job_id}",
            **_reply_kwargs(reply_to_message_id),
        )
        return False


async def _maybe_publish_youtube_pdf(
    *,
    broker: RabbitBroker,
    result: TxtDoneSuccess,
    transcript_text: str,
) -> None:
    """
    If source is YouTube and transcript is non-empty, publish a PDF order.
    The user receives an additional PDF with title, channel and date.
    Publish errors are non-fatal: transcript already delivered, exception is logged.
    """
    if result.delivery.source_type != "youtube":
        return
    if not transcript_text:
        return
    try:
        pdf_order = build_youtube_pdf_order(
            chat_id=result.reply.chat_id,
            transcript_text=transcript_text,
            metadata=result.youtube_metadata,
            summary=result.summary,
            extract_mode=result.extract_mode,
        )
        await broker.publish(pdf_order, queue="pdf.generate")
        title = (result.youtube_metadata or {}).get("title", "")
        logger.info(
            "event=youtube_pdf_published job_id=%s chat_id=%s title=%r",
            result.job_id,
            result.reply.chat_id,
            title,
        )
    except Exception as exc:
        logger.exception(
            "event=youtube_pdf_publish_failed job_id=%s chat_id=%s err=%s",
            result.job_id,
            result.reply.chat_id,
            exc,
        )


def register_txt_done_consumer(
    broker: RabbitBroker,
    bot: Bot,
    storage: LocalFileStorage,
) -> None:
    @broker.subscriber("txt.progress")
    async def txt_progress_consumer(data: dict) -> None:
        chat_id = data.get("chat_id")
        current = data.get("current", 0)
        total = data.get("total", 0)
        title = data.get("title", "")
        if not chat_id:
            return
        try:
            await bot.send_message(
                chat_id,
                f"Transcribing video {current}/{total}: {title}",
            )
        except Exception as exc:
            logger.warning(
                "event=progress_send_failed chat_id=%s current=%s/%s err=%s",
                chat_id,
                current,
                total,
                exc,
            )

    @broker.subscriber("txt.done")
    async def txt_done_consumer(data: dict) -> None:
        try:
            parsed = parse_txt_done_message(data)
        except Exception as exc:
            logger.exception("Invalid txt.done payload, drop. err=%s payload=%s", exc, data)
            return

        if isinstance(parsed, TxtDoneError):
            chat_id = parsed.reply.chat_id if parsed.reply else None
            reply_to_message_id = parsed.reply.reply_to_message_id if parsed.reply else None
            source_type = parsed.delivery.source_type if parsed.delivery else None
            target_kind = _target_kind_from_source_type(source_type)
            delivery_mode = parsed.delivery.mode if parsed.delivery else None

            logger.error(
                "event=vtt_done_error job_id=%s chat_id=%s source_type=%s "
                "target_kind=%s delivery_mode=%s error_code=%s error=%s",
                parsed.job_id,
                chat_id,
                source_type,
                target_kind,
                delivery_mode,
                parsed.error_code,
                parsed.error,
            )

            if chat_id is not None:
                code_part = f"\ncode: {parsed.error_code}" if parsed.error_code else ""
                await bot.send_message(
                    chat_id,
                    f"Transcription failed.\njob_id: {parsed.job_id}{code_part}",
                    **_reply_kwargs(reply_to_message_id),
                )
            return

        result: TxtDoneSuccess = parsed
        chat_id = result.reply.chat_id
        reply_to_message_id = result.reply.reply_to_message_id
        source_type = result.delivery.source_type
        delivery_mode = result.delivery.mode
        target_kind = _target_kind_from_source_type(source_type)

        logger.info(
            "event=vtt_done_received job_id=%s chat_id=%s source_type=%s "
            "target_kind=%s delivery_mode=%s txt_key=%s cached=%s youtube=%s",
            result.job_id,
            chat_id,
            source_type,
            target_kind,
            delivery_mode,
            result.txt_storage_key,
            result.cached,
            bool(result.youtube_metadata),
        )

        try:
            txt_bytes = await storage.read_bytes(result.txt_storage_key)
        except Exception as exc:
            logger.exception(
                "event=vtt_read_transcript_failed job_id=%s chat_id=%s key=%s err=%s",
                result.job_id,
                chat_id,
                result.txt_storage_key,
                exc,
            )
            await bot.send_message(
                chat_id,
                f"Transcript is ready but could not read the result.\njob_id: {result.job_id}",
                **_reply_kwargs(reply_to_message_id),
            )
            return

        transcript_text = txt_bytes.decode("utf-8", errors="replace").strip()

        # Voice: split into chunks
        if source_type == "voice":
            chunks = _chunk_text(transcript_text)

            if len(chunks) > _VOICE_MAX_TEXT_CHUNKS:
                try:
                    await bot.send_message(
                        chat_id,
                        "Transcript is too long, sending as file.",
                        **_reply_kwargs(reply_to_message_id),
                    )
                except Exception as exc:
                    logger.exception(
                        "event=vtt_send_notice_failed job_id=%s chat_id=%s err=%s",
                        result.job_id,
                        chat_id,
                        exc,
                    )

                await _send_transcript_document(
                    bot=bot,
                    chat_id=chat_id,
                    reply_to_message_id=reply_to_message_id,
                    txt_bytes=txt_bytes,
                    job_id=result.job_id,
                    source_type=source_type,
                    target_kind=target_kind,
                    caption=None,
                )
                return

            for index, chunk in enumerate(chunks):
                try:
                    await bot.send_message(
                        chat_id,
                        chunk if chunk else "(empty transcript)",
                        **(_reply_kwargs(reply_to_message_id) if index == 0 else {}),
                    )
                except Exception as exc:
                    logger.exception(
                        "event=vtt_send_result_failed job_id=%s chat_id=%s "
                        "delivery=text idx=%s err=%s",
                        result.job_id,
                        chat_id,
                        index,
                        exc,
                    )
                    await bot.send_message(
                        chat_id,
                        f"Transcript is ready but could not send text.\njob_id: {result.job_id}",
                        **(_reply_kwargs(reply_to_message_id) if index == 0 else {}),
                    )
                    return

            logger.info(
                "event=vtt_send_result_ok job_id=%s chat_id=%s source_type=%s "
                "delivery=text chunks=%s",
                result.job_id,
                chat_id,
                source_type,
                len(chunks),
            )
            return

        # YouTube / video / audio: short text -> message
        if _should_send_as_short_message(source_type, transcript_text):
            try:
                await bot.send_message(
                    chat_id,
                    transcript_text if transcript_text else "(empty transcript)",
                    **_reply_kwargs(reply_to_message_id),
                )
                logger.info(
                    "event=vtt_send_result_ok job_id=%s chat_id=%s "
                    "source_type=%s delivery=text chunks=1",
                    result.job_id,
                    chat_id,
                    source_type,
                )
            except Exception as exc:
                logger.exception(
                    "event=vtt_send_result_failed job_id=%s chat_id=%s "
                    "delivery=text idx=0 err=%s",
                    result.job_id,
                    chat_id,
                    exc,
                )
                await bot.send_message(
                    chat_id,
                    f"Transcript is ready but could not send text.\njob_id: {result.job_id}",
                    **_reply_kwargs(reply_to_message_id),
                )

            # YouTube: also build a PDF with title and metadata
            await _maybe_publish_youtube_pdf(
                broker=broker,
                result=result,
                transcript_text=transcript_text,
            )
            return

        # Long text -> file
        await _send_transcript_document(
            bot=bot,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            txt_bytes=txt_bytes,
            job_id=result.job_id,
            source_type=source_type,
            target_kind=target_kind,
            caption=_DOCUMENT_CAPTION,
        )

        # YouTube: also build a PDF even when transcript was sent as file
        await _maybe_publish_youtube_pdf(
            broker=broker,
            result=result,
            transcript_text=transcript_text,
        )
