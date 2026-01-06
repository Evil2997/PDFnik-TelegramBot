import json
from io import BytesIO

from aiogram import Dispatcher, Bot
from aiogram.types import Message
from faststream.rabbit import RabbitBroker
from faststream.redis import Redis

from pdfnik_contracts.pdf_content import (
    PdfTextBlock,
    PdfImageBlock,
    PdfRichText,
    PdfTextEntity,
    TextEntityType, PdfImageRef,
)

from main_app.core.logger import logger
from main_app.domain.build_stats_message import build_stats_message
from main_app.infrastructure.storage import LocalFileStorage


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
    broker: RabbitBroker,
    redis: Redis,
    bot: Bot,
    storage: LocalFileStorage,
) -> None:
    @dp.message()
    async def user_message(msg: Message):
        chat_id = msg.chat.id
        key = f"pdf_session:{chat_id}"
        logger.info(f"Incoming message from chat {chat_id}")

        # DONE
        if msg.text and msg.text.strip().lower() in ("done", "готово"):
            data = await redis.lrange(key, 0, -1)

            if not data:
                await msg.answer("Пока нечего собирать — отправьте текст или фото 🙂")
                return

            items = [json.loads(x) for x in data]

            from pdfnik_contracts.pdf_content import PdfBlockType  # добавь к импортам

            def _get_type(x: dict) -> str:
                # x["type"] может быть строкой, enum, или отсутствовать (на всякий)
                t = x.get("type")
                return str(t) if t is not None else ""

            texts = sum(1 for x in items if _get_type(x) in (PdfBlockType.TEXT, str(PdfBlockType.TEXT), "text"))
            images = sum(1 for x in items if _get_type(x) in (PdfBlockType.IMAGE, str(PdfBlockType.IMAGE), "image"))

            # на будущее: если вдруг в очереди окажутся уже нормализованные блоки
            # paragraphs = sum(
            #     1 for x in items if _get_type(x) in (PdfBlockType.PARAGRAPH, str(PdfBlockType.PARAGRAPH), "paragraph"))
            # lists = sum(1 for x in items if _get_type(x) in (PdfBlockType.LIST, str(PdfBlockType.LIST), "list"))
            # prices = sum(1 for x in items if
            #              _get_type(x) in (PdfBlockType.PRICE_TABLE, str(PdfBlockType.PRICE_TABLE), "price_table"))
            # headings = sum(
            #     1 for x in items if _get_type(x) in (PdfBlockType.HEADING, str(PdfBlockType.HEADING), "heading"))

            await msg.answer(build_stats_message(0, images, texts))

            await broker.publish(
                message={"chat_id": chat_id, "items": items},
                queue="pdf.generate",
            )
            await redis.delete(key)
            return

        # PHOTO (image block)
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
                ) if msg.caption else None,
            )

            await redis.rpush(key, block.model_dump_json())
            return

        # TEXT block
        if msg.text:
            block = PdfTextBlock(
                content=PdfRichText(
                    text=msg.text,
                    entities=_convert_entities(msg.entities),
                )
            )
            await redis.rpush(key, block.model_dump_json())
            return
