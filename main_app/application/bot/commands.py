# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/commands.py
# repo: PDFnik-TelegramBot

import json

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from main_app.application.bot.commands_text import (
    CANCEL_CONFIRM_TEXT,
    CANCEL_CONFIRMED_TEXT,
    CANCEL_EMPTY_TEXT,
    HELP_TEXT,
    START_TEXT,
)
from main_app.application.bot.session_manager import cancel_pause_check
from main_app.core.logger import logger
from main_app.domain.build_stats_message import build_stats_message
from main_app.infrastructure.rabbit_connector import broker
from main_app.infrastructure.redis_connector import redis

# TTL for the cancel confirmation flag in seconds.
# If the user does not confirm within this window, the session is preserved.
_CANCEL_PENDING_TTL = 60


def _cancel_pending_key(chat_id: int) -> str:
    return f"pdf_session:cancel_pending:{chat_id}"


def _session_key(chat_id: int) -> str:
    return f"pdf_session:{chat_id}"


def _to_str(x: object) -> str:
    if isinstance(x, bytes):
        return x.decode("utf-8")
    return str(x)


def _count_items(items: list[dict]) -> tuple[int, int]:
    """Returns (photo_count, text_count) from a session items list."""
    images = sum(1 for x in items if "image" in x)
    texts_plain = sum(1 for x in items if "content" in x)
    texts_captions = sum(
        1
        for x in items
        if "image" in x
        and isinstance(x.get("caption"), dict)
        and (x["caption"].get("text") or "").strip()
    )
    return images, texts_plain + texts_captions


def register_command_handlers(dp: Dispatcher) -> None:
    @dp.message(Command("start"))
    async def command_start(msg: Message) -> None:
        logger.info("/start from chat %s", msg.chat.id)
        await msg.answer(START_TEXT)

    @dp.message(Command("help"))
    async def command_help(msg: Message) -> None:
        logger.info("/help from chat %s", msg.chat.id)
        await msg.answer(HELP_TEXT)

    @dp.message(Command("done"))
    async def command_done(msg: Message) -> None:
        chat_id = msg.chat.id
        logger.info("/done from chat %s", chat_id)

        # /done clears any pending cancel confirmation
        await redis.delete(_cancel_pending_key(chat_id))
        await cancel_pause_check(chat_id, redis)

        key = _session_key(chat_id)
        data = await redis.lrange(key, 0, -1)

        if not data:
            await msg.answer("Nothing to collect yet — send some text or photos 🙂")
            return

        items = [json.loads(_to_str(x)) for x in data]
        images, texts = _count_items(items)

        await msg.answer(build_stats_message(0, images, texts))
        await broker.publish(
            message={"chat_id": chat_id, "items": items},
            queue="pdf.generate",
        )
        await redis.delete(key)

    @dp.message(Command("cancel"))
    async def command_cancel(msg: Message) -> None:
        chat_id = msg.chat.id
        logger.info("/cancel from chat %s", chat_id)

        key = _session_key(chat_id)
        pending_key = _cancel_pending_key(chat_id)

        data = await redis.lrange(key, 0, -1)

        # Empty session — nothing to confirm
        if not data:
            await redis.delete(pending_key)
            await msg.answer(CANCEL_EMPTY_TEXT)
            return

        items = [json.loads(_to_str(x)) for x in data]
        images, texts = _count_items(items)

        # Check if confirmation is already pending
        is_pending = await redis.exists(pending_key)

        if is_pending:
            # Second /cancel — user confirmed, clear the session
            logger.info(
                "event=cancel_confirmed chat_id=%s photos=%s texts=%s",
                chat_id,
                images,
                texts,
            )
            await cancel_pause_check(chat_id, redis)
            await redis.delete(key)
            await redis.delete(pending_key)

            await msg.answer(
                CANCEL_CONFIRMED_TEXT.format(
                    photo_count=images,
                    text_count=texts,
                )
            )
        else:
            # First /cancel — ask for confirmation
            logger.info(
                "event=cancel_pending chat_id=%s photos=%s texts=%s",
                chat_id,
                images,
                texts,
            )
            await redis.set(pending_key, "1", ex=_CANCEL_PENDING_TTL)

            await msg.answer(
                CANCEL_CONFIRM_TEXT.format(
                    photo_count=images,
                    text_count=texts,
                )
            )
