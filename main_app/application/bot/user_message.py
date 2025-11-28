import json
from io import BytesIO

from aiogram.types import Message
from pdfnik_contracts.pdf_content import PdfImageItem, PdfTextItem

from main_app.core.logger import logger
from main_app.domain.build_stats_message import build_stats_message
from main_app.infrastructure.bot_factory import dp, bot
from main_app.infrastructure.rabbit_connector import broker
from main_app.infrastructure.redis_connector import redis
from main_app.infrastructure.storage import storage


@dp.message()
async def user_message(msg: Message):
    chat_id = msg.chat.id
    key = f"pdf_session:{chat_id}"
    logger.info(f"Incoming message from chat {chat_id}")

    if msg.text and msg.text.strip().lower() in ("done", "готово"):
        logger.info(f"DONE command from chat {chat_id}")
        data = await redis.lrange(key, 0, -1)

        if not data:
            logger.warning(f"DONE but no session items for chat {chat_id}")
            await msg.answer("Пока нечего собирать — отправьте текст или фото 🙂")
            return

        items = [json.loads(x) for x in data]

        files = sum(1 for x in items if x.get("type") == "file")
        photos = sum(1 for x in items if x.get("type") == "image")
        texts = sum(1 for x in items if x.get("type") == "text")

        logger.info(
            f"Session summary for chat {chat_id}: "
            f"{files} files, {photos} photos, {texts} texts"
        )
        await msg.answer(build_stats_message(files, photos, texts))

        try:
            await broker.publish(
                message={"chat_id": chat_id, "items": items},
                queue="pdf.generate",
            )
            logger.info(f"PDF job published for chat {chat_id} to pdf.generate")
        except Exception as e:
            logger.error(f"Failed to publish PDF job for chat {chat_id}: {e}")
        finally:
            await redis.delete(key)
        return

    if msg.text:
        logger.info(f"Saving text message for chat {chat_id}")
        item = PdfTextItem(text=msg.text)
        await redis.rpush(key, item.model_dump_json())
        return

    if msg.photo:
        logger.info(f"Saving photo message for chat {chat_id}")
        p = msg.photo[-1]

        buf = BytesIO()
        await bot.download(p, destination=buf)
        img_bytes = buf.getvalue()

        try:
            stored = await storage.save_bytes(
                img_bytes,
                prefix="images",
                filename=f"{p.file_unique_id}.jpg",
                content_type="image/jpeg",
            )
            item = PdfImageItem(
                filename=stored.filename,
                storage_key=stored.storage_key,
            )
            await redis.rpush(key, item.model_dump_json())
            logger.info(f"Photo stored for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to save photo for chat {chat_id}: {e}")
        return
