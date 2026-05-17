# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/commands.py
# repo: PDFnik-TelegramBot

import json

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from main_app.application.bot.commands_text import (
    CANCEL_EMPTY_TEXT,
    CANCEL_WITH_CONTENT_TEXT,
    HELP_TEXT,
    START_TEXT,
)
from main_app.application.bot.session_manager import cancel_pause_check
from main_app.core.logger import logger
from main_app.domain.build_stats_message import build_stats_message
from main_app.infrastructure.rabbit_connector import broker
from main_app.infrastructure.redis_connector import redis


def register_command_handlers(dp: Dispatcher) -> None:

    @dp.message(Command("start"))
    async def command_start(msg: Message) -> None:
        logger.info(f"/start from chat {msg.chat.id}")
        await msg.answer(START_TEXT)

    @dp.message(Command("help"))
    async def command_help(msg: Message) -> None:
        logger.info(f"/help from chat {msg.chat.id}")
        await msg.answer(HELP_TEXT)

    @dp.message(Command("done"))
    async def command_done(msg: Message) -> None:
        chat_id = msg.chat.id
        logger.info(f"/done from chat {chat_id}")

        await cancel_pause_check(chat_id, redis)

        key = f"pdf_session:{chat_id}"
        data = await redis.lrange(key, 0, -1)

        if not data:
            await msg.answer("Пока нечего собирать — отправьте текст или фото 🙂")
            return

        def _to_str(x: object) -> str:
            if isinstance(x, bytes):
                return x.decode("utf-8")
            return str(x)

        items = [json.loads(_to_str(x)) for x in data]

        images = sum(1 for x in items if "image" in x)
        texts_plain = sum(1 for x in items if "content" in x)
        texts_captions = sum(
            1
            for x in items
            if "image" in x
            and isinstance(x.get("caption"), dict)
            and (x["caption"].get("text") or "").strip()
        )
        texts = texts_plain + texts_captions

        await msg.answer(build_stats_message(0, images, texts))

        await broker.publish(
            message={"chat_id": chat_id, "items": items},
            queue="pdf.generate",
        )

        await redis.delete(key)

    @dp.message(Command("cancel"))
    async def command_cancel(msg: Message) -> None:
        chat_id = msg.chat.id
        logger.info(f"/cancel from chat {chat_id}")

        key = f"pdf_session:{chat_id}"
        data = await redis.lrange(key, 0, -1)

        if not data:
            await msg.answer(CANCEL_EMPTY_TEXT)
            return

        def _to_str(x: object) -> str:
            if isinstance(x, bytes):
                return x.decode("utf-8")
            return str(x)

        items = [json.loads(_to_str(x)) for x in data]

        images = sum(1 for x in items if "image" in x)
        texts_plain = sum(1 for x in items if "content" in x)
        texts_captions = sum(
            1
            for x in items
            if "image" in x
            and isinstance(x.get("caption"), dict)
            and (x["caption"].get("text") or "").strip()
        )
        texts = texts_plain + texts_captions

        await cancel_pause_check(chat_id, redis)
        await redis.delete(key)

        await msg.answer(
            CANCEL_WITH_CONTENT_TEXT.format(
                photo_count=images,
                text_count=texts,
            )
        )