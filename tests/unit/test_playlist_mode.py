# repo: PDFnik-TelegramBot

"""
Tests for playlist_mode.py helpers (previously uncovered).

Covers:
- pending-playlist Redis key helpers (store / pop / miss)
- make_mode_keyboard layout, including the appended close row (feature 11)
- publish_playlist_job success/failure
- auto-mode timer (feature 1): fire, cancel, close interplay
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from main_app.application.bot import closeable, playlist_mode
from main_app.application.bot.closeable import CLOSE_CALLBACK_DATA
from main_app.application.bot.playlist_mode import (
    _MODES,
    _PENDING_TTL_SEC,
    AUTO_MODE,
    AUTO_MODE_NOTICE,
    AUTO_MODE_TIMEOUT_SEC,
    SESSION_EXPIRED_TEXT,
    _pending_key,
    cancel_auto_mode,
    make_mode_keyboard,
    pop_pending_playlist,
    publish_playlist_job,
    schedule_auto_mode,
    store_pending_playlist,
)

# ---------------------------------------------------------------------------
# Pending playlist storage
# ---------------------------------------------------------------------------


class TestPendingKey:
    def test_format(self):
        assert _pending_key(12, 34) == "playlist_mode_pending:12:34"

    def test_distinct_per_message(self):
        assert _pending_key(1, 2) != _pending_key(1, 3)


class TestStorePendingPlaylist:
    async def test_sets_with_ttl(self):
        redis = MagicMock()
        redis.set = AsyncMock()

        await store_pending_playlist(redis, 12, 34, "https://youtu.be/x")

        redis.set.assert_awaited_once_with(
            "playlist_mode_pending:12:34", "https://youtu.be/x", ex=_PENDING_TTL_SEC
        )


class TestPopPendingPlaylist:
    async def test_returns_and_deletes_on_hit(self):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=b"https://youtu.be/x")
        redis.delete = AsyncMock()

        url = await pop_pending_playlist(redis, 12, 34)

        assert url == "https://youtu.be/x"
        redis.delete.assert_awaited_once_with("playlist_mode_pending:12:34")

    async def test_decodes_str_value(self):
        redis = MagicMock()
        redis.get = AsyncMock(return_value="https://youtu.be/y")
        redis.delete = AsyncMock()

        assert await pop_pending_playlist(redis, 1, 2) == "https://youtu.be/y"

    async def test_returns_none_on_miss(self):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.delete = AsyncMock()

        assert await pop_pending_playlist(redis, 1, 2) is None
        redis.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# Mode keyboard
# ---------------------------------------------------------------------------


class TestMakeModeKeyboard:
    def test_mode_buttons_two_per_row(self):
        kb = make_mode_keyboard(original_message_id=7)
        mode_rows = kb.inline_keyboard[:-1]  # last row is the close row
        buttons = [btn for row in mode_rows for btn in row]
        assert len(buttons) == len(_MODES)
        assert all(len(row) <= 2 for row in mode_rows)

    def test_mode_labels(self):
        kb = make_mode_keyboard(original_message_id=7)
        labels = [btn.text for row in kb.inline_keyboard[:-1] for btn in row]
        assert labels == [label for _, label in _MODES]

    def test_callback_data_carries_mode_and_message_id(self):
        kb = make_mode_keyboard(original_message_id=7)
        first = kb.inline_keyboard[0][0]
        assert first.callback_data is not None
        assert first.callback_data.startswith("plm:")
        assert ":7" in first.callback_data

    def test_last_row_is_close_button(self):
        kb = make_mode_keyboard(original_message_id=7)
        close_row = kb.inline_keyboard[-1]
        assert len(close_row) == 1
        assert close_row[0].callback_data == CLOSE_CALLBACK_DATA


# ---------------------------------------------------------------------------
# publish_playlist_job
# ---------------------------------------------------------------------------


class TestPublishPlaylistJob:
    async def test_success(self):
        broker = MagicMock()
        broker.publish = AsyncMock()

        job_id, published = await publish_playlist_job(
            broker, chat_id=1, orig_msg_id=2, mode="learn", url="https://youtu.be/x"
        )

        assert published is True
        assert job_id
        broker.publish.assert_awaited_once()
        payload = broker.publish.call_args[0][0]
        assert payload["extract_mode"] == "learn"
        assert payload["target"]["value"] == "https://youtu.be/x"
        assert broker.publish.call_args.kwargs["queue"] == "txt.transcribe"

    async def test_failure_returns_false(self):
        broker = MagicMock()
        broker.publish = AsyncMock(side_effect=RuntimeError("broker down"))

        job_id, published = await publish_playlist_job(
            broker, chat_id=1, orig_msg_id=2, mode="summary", url="https://youtu.be/x"
        )

        assert published is False
        assert job_id


# ---------------------------------------------------------------------------
# Auto-mode timer (feature 1)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registries():
    yield
    for task in playlist_mode._auto_mode_timers.values():
        task.cancel()
    playlist_mode._auto_mode_timers.clear()
    closeable._close_cleanups.clear()


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


def _make_broker() -> MagicMock:
    broker = MagicMock()
    broker.publish = AsyncMock()
    return broker


def _make_redis(url: str | None = "https://youtu.be/x") -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=url)
    redis.delete = AsyncMock()
    return redis


class TestAutoModeConstants:
    def test_pending_ttl_outlives_timer(self):
        assert _PENDING_TTL_SEC > AUTO_MODE_TIMEOUT_SEC

    def test_auto_mode_is_summary(self):
        assert AUTO_MODE == "summary"
        assert AUTO_MODE in dict(_MODES)


class TestScheduleAutoMode:
    async def test_fires_and_starts_summary(self):
        bot, broker, redis = _make_bot(), _make_broker(), _make_redis()

        task = schedule_auto_mode(
            bot, broker, redis, chat_id=1, orig_msg_id=2, prompt_message_id=3, delay=0
        )
        await task

        bot.edit_message_text.assert_awaited_once_with(
            text=AUTO_MODE_NOTICE, chat_id=1, message_id=3
        )
        payload = broker.publish.call_args[0][0]
        assert payload["extract_mode"] == AUTO_MODE
        # timer removed itself from the registry
        assert (1, 2) not in playlist_mode._auto_mode_timers

    async def test_fires_on_expired_session(self):
        bot, broker = _make_bot(), _make_broker()
        redis = _make_redis(url=None)

        task = schedule_auto_mode(
            bot, broker, redis, chat_id=1, orig_msg_id=2, prompt_message_id=3, delay=0
        )
        await task

        bot.edit_message_text.assert_awaited_once_with(
            text=SESSION_EXPIRED_TEXT, chat_id=1, message_id=3
        )
        broker.publish.assert_not_awaited()

    async def test_publish_failure_notifies_user(self):
        bot, redis = _make_bot(), _make_redis()
        broker = MagicMock()
        broker.publish = AsyncMock(side_effect=RuntimeError("down"))

        task = schedule_auto_mode(
            bot, broker, redis, chat_id=1, orig_msg_id=2, prompt_message_id=3, delay=0
        )
        await task

        bot.send_message.assert_awaited_once()
        assert "Could not start processing" in bot.send_message.call_args[0][1]

    async def test_cancel_prevents_firing(self):
        bot, broker, redis = _make_bot(), _make_broker(), _make_redis()

        task = schedule_auto_mode(
            bot, broker, redis, chat_id=1, orig_msg_id=2, prompt_message_id=3, delay=60
        )
        cancel_auto_mode(1, 2)
        await asyncio.gather(task, return_exceptions=True)

        broker.publish.assert_not_awaited()
        bot.edit_message_text.assert_not_awaited()
        assert (1, 2) not in playlist_mode._auto_mode_timers

    async def test_reschedule_cancels_previous_timer(self):
        bot, broker, redis = _make_bot(), _make_broker(), _make_redis()

        first = schedule_auto_mode(
            bot, broker, redis, chat_id=1, orig_msg_id=2, prompt_message_id=3, delay=60
        )
        second = schedule_auto_mode(
            bot, broker, redis, chat_id=1, orig_msg_id=2, prompt_message_id=3, delay=60
        )

        await asyncio.gather(first, return_exceptions=True)
        assert first.cancelled() or first.done()
        assert playlist_mode._auto_mode_timers[(1, 2)] is second

    async def test_close_cleanup_cancels_timer_and_drops_pending(self):
        bot, broker, redis = _make_bot(), _make_broker(), _make_redis()

        task = schedule_auto_mode(
            bot, broker, redis, chat_id=1, orig_msg_id=2, prompt_message_id=3, delay=60
        )
        cleanup = closeable.pop_close_cleanup(1, 3)
        assert cleanup is not None

        await cleanup()
        await asyncio.gather(task, return_exceptions=True)

        assert (1, 2) not in playlist_mode._auto_mode_timers
        redis.delete.assert_awaited_once_with(_pending_key(1, 2))
        broker.publish.assert_not_awaited()

    async def test_firing_removes_own_close_cleanup(self):
        bot, broker, redis = _make_bot(), _make_broker(), _make_redis()

        task = schedule_auto_mode(
            bot, broker, redis, chat_id=1, orig_msg_id=2, prompt_message_id=3, delay=0
        )
        await task

        assert closeable.pop_close_cleanup(1, 3) is None
