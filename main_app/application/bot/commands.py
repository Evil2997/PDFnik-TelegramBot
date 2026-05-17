"""
Хендлеры команд /start, /help, /cancel.

Регистрация в main.py / router setup:
    from bot_commands import register_command_handlers
    register_command_handlers(router, session_store)

session_store — любой объект с методами:
    async def clear(chat_id: int) -> None
    async def get_stats(chat_id: int) -> dict | None

Это позволяет передавать Redis-based или in-memory store
без жёсткой зависимости.
"""
import json
from typing import Protocol

from aiogram import Dispatcher
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

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

        # items = [json.loads(...)] уже есть

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

# ---------------------------------------------------------------------------
# Protocol для session store (dependency inversion)
# ---------------------------------------------------------------------------

class SessionStore(Protocol):
    async def clear(self, chat_id: int) -> None: ...
    async def get_stats(self, chat_id: int) -> dict | None: ...

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_command_handlers(router: Router, session_store: SessionStore) -> None:
    """
    Реєструє хендлери /start, /help, /cancel на переданому router.
    Викликати один раз при старті бота.
    """

    @router.message(Command("start"))
    async def handle_start(message: Message) -> None:
        await message.answer(_START_TEXT, parse_mode=None)

    @router.message(Command("help"))
    async def handle_help(message: Message) -> None:
        await message.answer(_HELP_TEXT, parse_mode=None)

    @router.message(Command("cancel"))
    async def handle_cancel(message: Message) -> None:
        chat_id = message.chat.id

        try:
            stats = await session_store.get_stats(chat_id)

            if not stats or _session_is_empty(stats):
                await message.answer(_CANCEL_EMPTY_TEXT)
                return

            await session_store.clear(chat_id)

            text = _CANCEL_WITH_CONTENT_TEXT.format(
                text_count=stats.get("text_count", 0),
                photo_count=stats.get("photo_count", 0),
                voice_count=stats.get("voice_count", 0),
            )
            await message.answer(text)

        except Exception:
            await message.answer(_CANCEL_ERROR_TEXT)


def _session_is_empty(stats: dict) -> bool:
    return (
        stats.get("text_count", 0) == 0
        and stats.get("photo_count", 0) == 0
        and stats.get("voice_count", 0) == 0
    )