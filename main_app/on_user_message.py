import json
from io import BytesIO

from aiogram.types import Message

from main_app.contracts import TextItem, ImageItem
from main_app.main_constants import broker, dp, bot, redis, storage
from main_app.utils import build_stats_message


@dp.message()
async def on_user_message(msg: Message):
    chat_id = msg.chat.id
    key = f"pdf_session:{chat_id}"

    # ---------------------------------------------
    #  Команда "готово" / "done"
    # ---------------------------------------------
    if msg.text and msg.text.strip().lower() in ("done", "готово"):
        data = await redis.lrange(key, 0, -1)

        if not data:
            await msg.answer("Пока нечего собирать — отправьте текст или фото 🙂")
            return

        items = [json.loads(x) for x in data]

        # подсчёт статистики
        files = sum(1 for x in items if x.get("type") == "file")
        photos = sum(1 for x in items if x.get("type") == "image")
        texts = sum(1 for x in items if x.get("type") == "text")

        await msg.answer(build_stats_message(files, photos, texts))

        # отправка большого батча в backend
        await broker.publish(
            message={
                "chat_id": chat_id,
                "items": items,  # весь накопленный список (уже без base64, только storage_key)
            },
            queue="orders",
        )

        await redis.delete(key)
        return

    # -------------------------------------------------------
    #  Сбор текстов
    # -------------------------------------------------------
    if msg.text:
        item = TextItem(type="text", text=msg.text)
        # сохраняем JSON строки модели в Redis
        await redis.rpush(key, item.model_dump_json())
        return
    # -------------------------------------------------------
    #  Сбор фото
    # -------------------------------------------------------
    if msg.photo:
        p = msg.photo[-1]  # лучшее качество

        # Скачиваем фото в память (байты)
        buf = BytesIO()
        await bot.download(p, destination=buf)
        img_bytes = buf.getvalue()

        # Сохраняем в "S3-подобное" хранилище
        stored = await storage.save_bytes(
            img_bytes,
            prefix="images",
            filename=f"{p.file_unique_id}.jpg",
            content_type="image/jpeg",
        )

        item = ImageItem(
            type="image",
            filename=stored.filename,
            storage_key=stored.storage_key,
        )
        await redis.rpush(key, item.model_dump_json())
        return