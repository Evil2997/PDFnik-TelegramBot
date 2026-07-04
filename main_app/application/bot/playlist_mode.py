import asyncio
import uuid

from aiogram import Bot, Dispatcher
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from faststream.rabbit import RabbitBroker
from faststream.redis import Redis

from main_app.application.bot.closeable import (
    pop_close_cleanup,
    register_close_cleanup,
    with_close_button,
)
from main_app.application.bot.vtt_contracts import (
    TxtDelivery,
    TxtReply,
    TxtTarget,
    TxtTranscribeJob,
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

# Feature 1: auto-select Summary if the user does not pick a mode in time.
# The pending TTL must outlive the auto-select timer, otherwise the timer
# fires against an already-expired session.
AUTO_MODE_TIMEOUT_SEC = 600
AUTO_MODE = "summary"
AUTO_MODE_NOTICE = "Mode not selected within 10 minutes. Starting with Summary automatically."
SESSION_EXPIRED_TEXT = "Session expired. Please send the link again."

_PENDING_TTL_SEC = 900
_PENDING_PREFIX = "playlist_mode_pending"

# In-process auto-mode timers keyed by (chat_id, orig_msg_id) - same approach
# as the silence timer in session_manager.py. Lost on bot restart, in which
# case the pending entry silently expires via its Redis TTL.
_auto_mode_timers: dict[tuple[int, int], asyncio.Task] = {}


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
    # Close row lets the user dismiss the prompt; closing also cancels the
    # auto-mode timer and drops the pending entry (see schedule_auto_mode).
    return with_close_button(InlineKeyboardMarkup(inline_keyboard=rows))


async def publish_playlist_job(
    broker: RabbitBroker,
    *,
    chat_id: int,
    orig_msg_id: int,
    mode: str,
    url: str,
) -> tuple[str, bool]:
    """Publishes a playlist transcription job. Returns (job_id, published)."""
    job_id = str(uuid.uuid4())
    payload = TxtTranscribeJob(
        job_id=job_id,
        target=TxtTarget(kind="url", value=url),
        reply=TxtReply(chat_id=chat_id, reply_to_message_id=orig_msg_id),
        delivery=TxtDelivery(source_type="youtube", mode="document"),
        extract_mode=mode,
        cfg={},
    )

    try:
        await broker.publish(payload.model_dump(exclude_none=True), queue="txt.transcribe")
    except Exception as exc:
        logger.exception(
            "event=playlist_job_publish_failed job_id=%s chat_id=%s err=%s",
            job_id,
            chat_id,
            exc,
        )
        return job_id, False

    logger.info(
        "event=playlist_job_published job_id=%s chat_id=%s mode=%s url=%s",
        job_id,
        chat_id,
        mode,
        url,
    )
    return job_id, True


async def _edit_prompt(bot: Bot, chat_id: int, message_id: int, text: str) -> None:
    try:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        logger.info(
            "event=playlist_prompt_edit_failed chat_id=%s message_id=%s err=%s",
            chat_id,
            message_id,
            exc,
        )


def cancel_auto_mode(chat_id: int, orig_msg_id: int) -> None:
    task = _auto_mode_timers.pop((chat_id, orig_msg_id), None)
    if task is not None:
        task.cancel()


def schedule_auto_mode(
    bot: Bot,
    broker: RabbitBroker,
    redis: Redis,
    *,
    chat_id: int,
    orig_msg_id: int,
    prompt_message_id: int,
    delay: float = AUTO_MODE_TIMEOUT_SEC,
) -> asyncio.Task:
    """
    Feature 1: starts the auto-mode timer for a pending mode-selection prompt.

    If the user neither picks a mode nor closes the prompt within `delay`
    seconds, Summary is selected automatically and processing starts. Manual
    selection (on_mode_selected) and the close button both cancel the timer.
    """
    key = (chat_id, orig_msg_id)
    cancel_auto_mode(chat_id, orig_msg_id)

    async def _timer() -> None:
        try:
            await asyncio.sleep(delay)

            pop_close_cleanup(chat_id, prompt_message_id)
            url = await pop_pending_playlist(redis, chat_id, orig_msg_id)
            if url is None:
                # Pending entry vanished without the timer being cancelled
                # (Redis restart/eviction) - ask the user to resend.
                await _edit_prompt(bot, chat_id, prompt_message_id, SESSION_EXPIRED_TEXT)
                return

            logger.info(
                "event=playlist_auto_mode chat_id=%s orig_msg_id=%s mode=%s",
                chat_id,
                orig_msg_id,
                AUTO_MODE,
            )
            await _edit_prompt(bot, chat_id, prompt_message_id, AUTO_MODE_NOTICE)

            job_id, published = await publish_playlist_job(
                broker, chat_id=chat_id, orig_msg_id=orig_msg_id, mode=AUTO_MODE, url=url
            )
            if not published:
                await bot.send_message(
                    chat_id, f"Could not start processing. Please try again.\njob_id: {job_id}"
                )
        except asyncio.CancelledError:
            return
        finally:
            if _auto_mode_timers.get(key) is asyncio.current_task():
                _auto_mode_timers.pop(key, None)

    task = asyncio.create_task(_timer())
    _auto_mode_timers[key] = task

    async def _on_close() -> None:
        cancel_auto_mode(chat_id, orig_msg_id)
        await pop_pending_playlist(redis, chat_id, orig_msg_id)

    register_close_cleanup(chat_id, prompt_message_id, _on_close)
    return task


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

        cancel_auto_mode(chat_id, orig_msg_id)
        pop_close_cleanup(chat_id, callback.message.message_id)

        url = await pop_pending_playlist(redis, chat_id, orig_msg_id)
        if not url:
            await callback.answer("Session expired. Please resend the URL.", show_alert=True)
            return

        label = _mode_labels.get(mode, mode)
        await callback.message.edit_text(f"Mode: {label}\nProcessing playlist, please wait...")
        await callback.answer()

        job_id, published = await publish_playlist_job(
            broker, chat_id=chat_id, orig_msg_id=orig_msg_id, mode=mode, url=url
        )
        if not published:
            await callback.message.answer(
                f"Could not start processing. Please try again.\njob_id: {job_id}"
            )
