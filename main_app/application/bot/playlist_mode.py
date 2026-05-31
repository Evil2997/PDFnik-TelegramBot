import uuid

from aiogram import Bot, Dispatcher
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from faststream.rabbit import RabbitBroker
from faststream.redis import Redis

from main_app.application.bot.vtt_contracts import (
    TxtDelivery,
    TxtReply,
    TxtTarget,
    TxtTranscribeRequest,
)
from main_app.core.logger import logger

_MODES: list[tuple[str, str]] = [
    ("summary", "Summary"),
    ("learn", "Learn"),
    ("commands", "Commands"),
    ("pipeline", "Pipeline"),
    ("tips", "Tips"),
    ("none", "Raw transcript"),
]

_PENDING_TTL_SEC = 300
_PENDING_PREFIX = "playlist_mode_pending"


class PlaylistModeCallback(CallbackData, prefix="plm"):
    mode: str
    orig_msg_id: int


def _pending_key(chat_id: int, message_id: int) -> str:
    return f"{_PENDING_PREFIX}:{chat_id}:{message_id}"


async def store_pending_playlist(redis: Redis, chat_id: int, message_id: int, url: str) -> None:
    await redis.set(_pending_key(chat_id, message_id), url, ex=_PENDING_TTL_SEC)


async def pop_pending_playlist(redis: Redis, chat_id: int, message_id: int) -> str | None:
    key = _pending_key(chat_id, message_id)
    raw = await redis.get(key)
    if raw:
        await redis.delete(key)
        return raw.decode() if isinstance(raw, bytes) else str(raw)
    return None


def make_mode_keyboard(original_message_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for mode_key, mode_label in _MODES:
        cb = PlaylistModeCallback(mode=mode_key, orig_msg_id=original_message_id)
        row.append(InlineKeyboardButton(text=mode_label, callback_data=cb.pack()))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def register_playlist_mode_handlers(
    dp: Dispatcher,
    bot: Bot,
    broker: RabbitBroker,
    redis: Redis,
) -> None:
    _mode_labels = dict(_MODES)

    @dp.callback_query(PlaylistModeCallback.filter())
    async def on_mode_selected(
        callback: CallbackQuery,
        callback_data: PlaylistModeCallback,
    ) -> None:
        if not isinstance(callback.message, Message):
            await callback.answer()
            return

        chat_id = callback.message.chat.id
        orig_msg_id = callback_data.orig_msg_id
        mode = callback_data.mode

        url = await pop_pending_playlist(redis, chat_id, orig_msg_id)
        if not url:
            await callback.answer("Session expired. Please resend the URL.", show_alert=True)
            return

        label = _mode_labels.get(mode, mode)
        await callback.message.edit_text(f"Mode: {label}\nProcessing playlist, please wait...")
        await callback.answer()

        job_id = str(uuid.uuid4())
        payload = TxtTranscribeRequest(
            job_id=job_id,
            target=TxtTarget(kind="url", value=url),
            reply=TxtReply(chat_id=chat_id, reply_to_message_id=orig_msg_id),
            delivery=TxtDelivery(source_type="youtube", mode="document"),
            extract_mode=mode,
            cfg={},
        )

        try:
            await broker.publish(payload.model_dump(exclude_none=True), queue="txt.transcribe")
            logger.info(
                "event=playlist_job_published job_id=%s chat_id=%s mode=%s url=%s",
                job_id,
                chat_id,
                mode,
                url,
            )
        except Exception as exc:
            logger.exception(
                "event=playlist_job_publish_failed job_id=%s chat_id=%s err=%s",
                job_id,
                chat_id,
                exc,
            )
            await callback.message.answer(
                f"Could not start processing. Please try again.\njob_id: {job_id}"
            )
