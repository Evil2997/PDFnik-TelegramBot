import json

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from pdfnik_contracts.pdf_content import PdfBlockType

from main_app.application.bot.commands_text import HELP_TEXT, START_TEXT
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

        # Отменяем таймер паузы, чтобы "пауза-сообщение" не отправилось после /done
        await cancel_pause_check(chat_id, redis)

        key = f"pdf_session:{chat_id}"
        data = await redis.lrange(key, 0, -1)

        if not data:
            await msg.answer("Пока нечего собирать — отправьте текст или фото 🙂")
            return

        # redis может вернуть bytes/str — json.loads умеет str, поэтому декодим bytes
        def _to_str(x: object) -> str:
            if isinstance(x, bytes):
                return x.decode("utf-8")
            return str(x)

        items = [json.loads(_to_str(x)) for x in data]

        def _get_type(x: dict) -> str:
            t = x.get("type")
            return str(t) if t is not None else ""

        texts = sum(
            1
            for x in items
            if _get_type(x) in (PdfBlockType.TEXT, str(PdfBlockType.TEXT), "text")
        )
        images = sum(
            1
            for x in items
            if _get_type(x) in (PdfBlockType.IMAGE, str(PdfBlockType.IMAGE), "image")
        )

        await msg.answer(build_stats_message(0, images, texts))

        await broker.publish(
            message={"chat_id": chat_id, "items": items},
            queue="pdf.generate",
        )

        await redis.delete(key)
