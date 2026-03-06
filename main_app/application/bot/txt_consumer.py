from __future__ import annotations

from typing import Iterable

from aiogram import Bot
from aiogram.types import BufferedInputFile
from faststream.rabbit import RabbitBroker

from main_app.core.logger import logger
from main_app.infrastructure.storage import LocalFileStorage
from .vtt_contracts import TxtDoneError, TxtDoneSuccess, parse_txt_done_message


_TELEGRAM_TEXT_LIMIT = 4096
_CHUNK_SIZE = 3800  # безопасно меньше лимита, чтобы не упираться в edge cases


def _reply_kwargs(reply_to_message_id: int | None) -> dict:
    if reply_to_message_id:
        return {"reply_to_message_id": reply_to_message_id}
    return {}


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE) -> Iterable[str]:
    """
    Простой чанкер: режем по символам.
    MVP: без умного разбиения по предложениям, но стабильно.
    """
    if not text:
        return [""]

    # на всякий случай не превышаем лимит
    chunk_size = min(chunk_size, _TELEGRAM_TEXT_LIMIT - 50)

    for i in range(0, len(text), chunk_size):
        yield text[i : i + chunk_size]


def register_txt_done_consumer(
    broker: RabbitBroker,
    bot: Bot,
    storage: LocalFileStorage,
) -> None:
    """
    Egress:
      - слушаем txt.done
      - успех:
          * читаем txt из storage по txt_storage_key
          * voice -> отправляем текстом (чанки)
          * video/youtube -> отправляем .txt документом
        (ВАЖНО) не пишем транскрипт в Redis session => PDF только из текстов пользователя
      - ошибка:
          * короткое сообщение + job_id (+ error_code если есть)
    """

    @broker.subscriber("txt.done")
    async def txt_done_consumer(data: dict) -> None:
        try:
            parsed = parse_txt_done_message(data)
        except Exception as e:
            logger.exception("Invalid txt.done payload, drop. err=%s payload=%s", e, data)
            return

        if isinstance(parsed, TxtDoneError):
            logger.error(
                "VTT failed: chat_id=%s job_id=%s source_type=%s code=%s err=%s",
                parsed.chat_id,
                parsed.job_id,
                parsed.source_type,
                parsed.error_code,
                parsed.error_message,
            )
            code_part = f"\ncode: {parsed.error_code}" if parsed.error_code else ""
            await bot.send_message(
                parsed.chat_id,
                f"Не удалось расшифровать.\njob_id: {parsed.job_id}{code_part}",
                **_reply_kwargs(parsed.reply_to_message_id),
            )
            return

        msg_ok: TxtDoneSuccess = parsed

        logger.info(
            "VTT done received: chat_id=%s job_id=%s source_type=%s txt_key=%s cached=%s",
            msg_ok.chat_id,
            msg_ok.job_id,
            msg_ok.source_type,
            msg_ok.txt_storage_key,
            msg_ok.cached,
        )

        # 1) Read transcript
        try:
            txt_bytes = await storage.read_bytes(msg_ok.txt_storage_key)
        except Exception as e:
            logger.exception(
                "Failed to read transcript from storage: chat_id=%s job_id=%s source_type=%s key=%s err=%s",
                msg_ok.chat_id,
                msg_ok.job_id,
                msg_ok.source_type,
                msg_ok.txt_storage_key,
                e,
            )
            await bot.send_message(
                msg_ok.chat_id,
                f"Расшифровка готова, но не смог прочитать результат.\njob_id: {msg_ok.job_id}",
                **_reply_kwargs(msg_ok.reply_to_message_id),
            )
            return

        txt_str = txt_bytes.decode("utf-8", errors="replace").strip()

        # 2) Deliver result depending on source_type
        if msg_ok.source_type == "voice":
            # Send as plain text; split if too long
            chunks = list(_chunk_text(txt_str))
            if not chunks:
                chunks = [""]

            for idx, chunk in enumerate(chunks):
                try:
                    await bot.send_message(
                        msg_ok.chat_id,
                        chunk if chunk else "(пустая расшифровка)",
                        **(_reply_kwargs(msg_ok.reply_to_message_id) if idx == 0 else {}),
                    )
                except Exception as e:
                    logger.exception(
                        "Failed to send transcript text chunk: chat_id=%s job_id=%s idx=%s err=%s",
                        msg_ok.chat_id,
                        msg_ok.job_id,
                        idx,
                        e,
                    )
                    # если упало на одном чанке — сообщим и прекратим
                    await bot.send_message(
                        msg_ok.chat_id,
                        f"Расшифровка готова, но не смог отправить текст.\njob_id: {msg_ok.job_id}",
                        **(_reply_kwargs(msg_ok.reply_to_message_id) if idx == 0 else {}),
                    )
                    return
            return

        # video/youtube (и любые остальные не-voice) -> отправляем как .txt документ
        filename = f"transcript_{msg_ok.job_id}.txt"
        try:
            file = BufferedInputFile(txt_bytes, filename)
            await bot.send_document(
                msg_ok.chat_id,
                file,
                **_reply_kwargs(msg_ok.reply_to_message_id),
            )
        except Exception as e:
            logger.exception(
                "Failed to send transcript as document: chat_id=%s job_id=%s source_type=%s err=%s",
                msg_ok.chat_id,
                msg_ok.job_id,
                msg_ok.source_type,
                e,
            )
            await bot.send_message(
                msg_ok.chat_id,
                f"Расшифровка готова, но не смог отправить файл.\njob_id: {msg_ok.job_id}",
                **_reply_kwargs(msg_ok.reply_to_message_id),
            )
            return

        logger.info(
            "VTT delivered: chat_id=%s job_id=%s source_type=%s",
            msg_ok.chat_id,
            msg_ok.job_id,
            msg_ok.source_type,
        )