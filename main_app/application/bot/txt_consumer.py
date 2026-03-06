from aiogram import Bot
from aiogram.types import BufferedInputFile
from faststream.rabbit import RabbitBroker

from main_app.application.bot.vtt_contracts import TxtDoneError
from main_app.application.bot.vtt_contracts import TxtDoneSuccess
from main_app.application.bot.vtt_contracts import parse_txt_done_message
from main_app.core.logger import logger
from main_app.infrastructure.storage import LocalFileStorage

_TELEGRAM_TEXT_LIMIT = 4096
_CHUNK_SIZE = 3800
_VOICE_MAX_TEXT_CHUNKS = 10


def _reply_kwargs(reply_to_message_id: int | None) -> dict:
    if reply_to_message_id:
        return {"reply_to_message_id": reply_to_message_id}
    return {}


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    if not text:
        return [""]

    safe_chunk_size = min(chunk_size, _TELEGRAM_TEXT_LIMIT - 50)
    chunks: list[str] = []

    for index in range(0, len(text), safe_chunk_size):
        chunks.append(text[index:index + safe_chunk_size])

    return chunks or [""]


def _target_kind_from_source_type(source_type: str | None) -> str:
    if source_type == "youtube":
        return "url"
    return "storage_key"


async def _send_transcript_document(
        *,
        bot: Bot,
        chat_id: int,
        reply_to_message_id: int | None,
        txt_bytes: bytes,
        job_id: str,
        source_type: str,
        target_kind: str,
) -> bool:
    filename = f"transcript_{job_id}.txt"
    try:
        file = BufferedInputFile(txt_bytes, filename)
        await bot.send_document(
            chat_id,
            file,
            **_reply_kwargs(reply_to_message_id),
        )
        logger.info(
            "event=vtt_send_result_ok job_id=%s chat_id=%s source_type=%s target_kind=%s delivery=document",
            job_id,
            chat_id,
            source_type,
            target_kind,
        )
        return True
    except Exception as exc:
        logger.exception(
            "event=vtt_send_result_failed job_id=%s chat_id=%s source_type=%s target_kind=%s delivery=document err=%s",
            job_id,
            chat_id,
            source_type,
            target_kind,
            exc,
        )
        await bot.send_message(
            chat_id,
            f"Расшифровка готова, но не смог отправить файл.\njob_id: {job_id}",
            **_reply_kwargs(reply_to_message_id),
        )
        return False


def register_txt_done_consumer(
        broker: RabbitBroker,
        bot: Bot,
        storage: LocalFileStorage,
) -> None:
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

            logger.error(
                "event=vtt_done_error job_id=%s chat_id=%s source_type=%s target_kind=%s error_code=%s error=%s",
                parsed.job_id,
                chat_id,
                source_type,
                target_kind,
                parsed.error_code,
                parsed.error,
            )

            if chat_id is not None:
                code_part = f"\ncode: {parsed.error_code}" if parsed.error_code else ""
                await bot.send_message(
                    chat_id,
                    f"Не удалось расшифровать.\njob_id: {parsed.job_id}{code_part}",
                    **_reply_kwargs(reply_to_message_id),
                )
            return

        result: TxtDoneSuccess = parsed
        chat_id = result.reply.chat_id
        reply_to_message_id = result.reply.reply_to_message_id
        source_type = result.delivery.source_type
        mode = result.delivery.mode
        target_kind = _target_kind_from_source_type(source_type)

        logger.info(
            "event=vtt_done_received job_id=%s chat_id=%s source_type=%s target_kind=%s mode=%s txt_key=%s cached=%s",
            result.job_id,
            chat_id,
            source_type,
            target_kind,
            mode,
            result.txt_storage_key,
            result.cached,
        )

        try:
            txt_bytes = await storage.read_bytes(result.txt_storage_key)
        except Exception as exc:
            logger.exception(
                "event=vtt_read_transcript_failed job_id=%s chat_id=%s source_type=%s target_kind=%s key=%s err=%s",
                result.job_id,
                chat_id,
                source_type,
                target_kind,
                result.txt_storage_key,
                exc,
            )
            await bot.send_message(
                chat_id,
                f"Расшифровка готова, но не смог прочитать результат.\njob_id: {result.job_id}",
                **_reply_kwargs(reply_to_message_id),
            )
            return

        transcript_text = txt_bytes.decode("utf-8", errors="replace").strip()

        if mode == "text":
            chunks = _chunk_text(transcript_text)

            if len(chunks) > _VOICE_MAX_TEXT_CHUNKS:
                try:
                    await bot.send_message(
                        chat_id,
                        "Транскрипт слишком длинный, отправляю файлом.",
                        **_reply_kwargs(reply_to_message_id),
                    )
                except Exception as exc:
                    logger.exception(
                        "event=vtt_send_notice_failed job_id=%s chat_id=%s source_type=%s target_kind=%s err=%s",
                        result.job_id,
                        chat_id,
                        source_type,
                        target_kind,
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
                )
                return

            for index, chunk in enumerate(chunks):
                try:
                    await bot.send_message(
                        chat_id,
                        chunk if chunk else "(пустая расшифровка)",
                        **(_reply_kwargs(reply_to_message_id) if index == 0 else {}),
                    )
                except Exception as exc:
                    logger.exception(
                        "event=vtt_send_result_failed job_id=%s chat_id=%s source_type=%s target_kind=%s delivery=text idx=%s err=%s",
                        result.job_id,
                        chat_id,
                        source_type,
                        target_kind,
                        index,
                        exc,
                    )
                    await bot.send_message(
                        chat_id,
                        f"Расшифровка готова, но не смог отправить текст.\njob_id: {result.job_id}",
                        **(_reply_kwargs(reply_to_message_id) if index == 0 else {}),
                    )
                    return

            logger.info(
                "event=vtt_send_result_ok job_id=%s chat_id=%s source_type=%s target_kind=%s delivery=text chunks=%s",
                result.job_id,
                chat_id,
                source_type,
                target_kind,
                len(chunks),
            )
            return

        await _send_transcript_document(
            bot=bot,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            txt_bytes=txt_bytes,
            job_id=result.job_id,
            source_type=source_type,
            target_kind=target_kind,
        )
