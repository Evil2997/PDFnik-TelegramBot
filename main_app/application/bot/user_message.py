# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/user_message.py
# repo: PDFnik-TelegramBot

from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from faststream.redis import Redis
from pdfnik_contracts.pdf_content import (
    PdfImageBlock,
    PdfImageRef,
    PdfRichText,
    PdfTextBlock,
    PdfTextEntity,
    TextEntityType,
)

from main_app.core.logger import logger
from main_app.infrastructure.storage import LocalFileStorage

from .session_manager import schedule_pause_check


def _convert_entities(entities):
    if not entities:
        return []
    result = []
    for e in entities:
        if e.type == "url":
            result.append(
                PdfTextEntity(
                    type=TextEntityType.URL,
                    offset=e.offset,
                    length=e.length,
                )
            )
        elif e.type == "text_link":
            result.append(
                PdfTextEntity(
                    type=TextEntityType.TEXT_LINK,
                    offset=e.offset,
                    length=e.length,
                    url=e.url,
                )
            )
    return result


def register_user_message_handlers(
    dp: Dispatcher,
    redis: Redis,
    bot: Bot,
    storage: LocalFileStorage,
) -> None:
    # Generic handler: ignores commands, accepts text/photos, saves to Redis session.
    @dp.message(~F.text.regexp(r"^/"))
    async def user_message(msg: Message):
        chat_id = msg.chat.id
        key = f"pdf_session:{chat_id}"
        logger.info(f"Incoming message from chat {chat_id}")

        # Photo — store as image block
        if msg.photo:
            p = msg.photo[-1]

            buf = BytesIO()
            await bot.download(p, destination=buf)
            img_bytes = buf.getvalue()

            stored = await storage.save_bytes(
                img_bytes,
                prefix="images",
                filename=f"{p.file_unique_id}.jpg",
                content_type="image/jpeg",
            )

            block = PdfImageBlock(
                image=PdfImageRef(
                    filename=stored.filename,
                    storage_key=stored.storage_key,
                ),
                caption=PdfRichText(
                    text=msg.caption,
                    entities=_convert_entities(msg.caption_entities),
                )
                if msg.caption
                else None,
            )

            await redis.rpush(key, block.model_dump_json())  # type: ignore[misc]

            # Restart silence timer on each new message.
            await schedule_pause_check(chat_id, bot, redis)
            return

        # Text — store as text block
        if msg.text:
            block = PdfTextBlock(
                content=PdfRichText(
                    text=msg.text,
                    entities=_convert_entities(msg.entities),
                )
            )
            await redis.rpush(key, block.model_dump_json())  # type: ignore[misc]

            # Restart silence timer on each new message.
            await schedule_pause_check(chat_id, bot, redis)
            return
