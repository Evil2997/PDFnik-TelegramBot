import base64
import json
import pathlib
from io import BytesIO

from aiogram.types import Message

from main_app.main_constants import broker, dp, bot, redis
from main_app.utils import build_stats_message
from main_app.contracts import PdfOrder, TextItem, ImageItem

IMAGES_DIR = pathlib.Path("images")
IMAGES_DIR.mkdir(exist_ok=True)


@dp.message()
async def on_user_message(msg: Message):
    chat_id = msg.chat.id
    key = f"pdf_session:{chat_id}"

    # команда "готово"
    if msg.text and msg.text.strip().lower() in ("done", "готово"):
        data = await redis.lrange(key, 0, -1)

        if not data:
            await msg.answer("Пока нечего собирать — отправьте текст или фото 🙂")
            return

        items = [json.loads(x) for x in data]

        # подсчёт статистики
        files = sum(1 for x in items if x["type"] == "file")
        photos = sum(1 for x in items if x["type"] == "image")
        texts = sum(1 for x in items if x["type"] == "text")

        await msg.answer(build_stats_message(files, photos, texts))

        # отправка большого батча в backend
        await broker.publish(
            message={
                "chat_id": chat_id,
                "items": items,  # весь накопленный список
            },
            queue="orders",
        )

        await redis.delete(key)
        return

    # -------------------------------------------------------
    #  Сбор текстов
    # -------------------------------------------------------
    if msg.text:
        payload = {"type": "text", "text": msg.text}
        await redis.rpush(key, json.dumps(payload))
        return

    # -------------------------------------------------------
    #  Сбор фото
    # -------------------------------------------------------
    if msg.photo:
        p = msg.photo[-1]  # лучшее качество
        buf = BytesIO()
        await bot.download(p, destination=buf)

        payload = {
            "type": "image",
            "filename": f"{p.file_unique_id}.jpg",
            "content_b64": base64.b64encode(buf.getvalue()).decode("utf-8"),
        }

        await redis.rpush(key, json.dumps(payload))
        return
