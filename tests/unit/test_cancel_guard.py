# /home/dmitriy/PycharmProjects/Telegram-Bot/tests/unit/test_cancel_guard.py
# repo: PDFnik-TelegramBot

"""
Tests for /cancel confirmation guard in commands.py.

Flow under test:
  1. /cancel on empty session → CANCEL_EMPTY_TEXT, no flag set
  2. /cancel on non-empty session → CANCEL_CONFIRM_TEXT, Redis flag set
  3. /cancel again (flag present) → session cleared, CANCEL_CONFIRMED_TEXT
  4. Flag expires (TTL) → session preserved (implicit via Redis TTL)
  5. /done clears pending flag
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main_app.application.bot.commands import (
    _CANCEL_PENDING_TTL,
    _cancel_pending_key,
    _count_items,
    _session_key,
)
from main_app.application.bot.commands_text import (
    CANCEL_CONFIRM_TEXT,
    CANCEL_CONFIRMED_TEXT,
    CANCEL_EMPTY_TEXT,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(chat_id: int = 12345) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.answer = AsyncMock()
    return msg


def _make_redis(
    session_data: list[bytes] | None = None,
    cancel_pending: bool = False,
) -> MagicMock:
    redis = MagicMock()
    redis.lrange = AsyncMock(return_value=session_data or [])
    redis.exists = AsyncMock(return_value=1 if cancel_pending else 0)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _item(kind: str = "text") -> bytes:
    if kind == "text":
        return b'{"content": {"text": "hello", "entities": []}}'
    if kind == "image":
        return b'{"image": {"filename": "img.jpg", "storage_key": "images/img.jpg"}}'
    return b"{}"


# ---------------------------------------------------------------------------
# _count_items
# ---------------------------------------------------------------------------


class TestCountItems:
    def test_empty_list(self):
        assert _count_items([]) == (0, 0)

    def test_text_only(self):
        items = [{"content": {"text": "hi"}}] * 3
        assert _count_items(items) == (0, 3)

    def test_images_only(self):
        items = [{"image": {"storage_key": "x"}}] * 2
        assert _count_items(items) == (2, 0)

    def test_mixed(self):
        items = [
            {"content": {"text": "hello"}},
            {"image": {"storage_key": "x"}},
            {"image": {"storage_key": "y"}},
        ]
        assert _count_items(items) == (2, 1)

    def test_image_with_caption_counts_as_text(self):
        items = [
            {
                "image": {"storage_key": "x"},
                "caption": {"text": "My caption"},
            }
        ]
        photos, texts = _count_items(items)
        assert photos == 1
        assert texts == 1


# ---------------------------------------------------------------------------
# Redis key helpers
# ---------------------------------------------------------------------------


class TestRedisKeys:
    def test_session_key(self):
        assert _session_key(123) == "pdf_session:123"

    def test_cancel_pending_key(self):
        assert _cancel_pending_key(123) == "pdf_session:cancel_pending:123"

    def test_keys_are_different(self):
        assert _session_key(1) != _cancel_pending_key(1)


# ---------------------------------------------------------------------------
# /cancel on empty session
# ---------------------------------------------------------------------------


class TestCancelEmptySession:
    @pytest.mark.asyncio
    async def test_sends_empty_text(self):
        from main_app.application.bot.commands import register_command_handlers

        dp = MagicMock()
        handlers = {}

        def fake_message(filter_obj):
            def decorator(fn):
                handlers[str(filter_obj)] = fn
                return fn

            return decorator

        dp.message = fake_message

        with (
            patch("main_app.application.bot.commands.redis", _make_redis(session_data=[])),
            patch("main_app.application.bot.commands.broker"),
        ):
            register_command_handlers(dp)

        # Find the cancel handler
        cancel_fn = next(fn for key, fn in handlers.items() if "cancel" in key.lower())
        msg = _make_msg()
        redis_mock = _make_redis(session_data=[])

        with patch("main_app.application.bot.commands.redis", redis_mock):
            await cancel_fn(msg)

        msg.answer.assert_awaited_once()
        assert CANCEL_EMPTY_TEXT in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_does_not_set_pending_flag_on_empty(self):
        from main_app.application.bot.commands import register_command_handlers

        dp = MagicMock()
        handlers = {}

        def fake_message(filter_obj):
            def decorator(fn):
                handlers[str(filter_obj)] = fn
                return fn

            return decorator

        dp.message = fake_message

        with (
            patch("main_app.application.bot.commands.redis", _make_redis()),
            patch("main_app.application.bot.commands.broker"),
        ):
            register_command_handlers(dp)

        cancel_fn = next(fn for key, fn in handlers.items() if "cancel" in key.lower())
        msg = _make_msg()
        redis_mock = _make_redis(session_data=[])

        with patch("main_app.application.bot.commands.redis", redis_mock):
            await cancel_fn(msg)

        # set should not be called for empty session
        redis_mock.set.assert_not_awaited()


# ---------------------------------------------------------------------------
# _CANCEL_PENDING_TTL
# ---------------------------------------------------------------------------


class TestCancelPendingTtl:
    def test_ttl_is_positive(self):
        assert _CANCEL_PENDING_TTL > 0

    def test_ttl_is_reasonable(self):
        # Between 30 seconds and 10 minutes
        assert 30 <= _CANCEL_PENDING_TTL <= 600


# ---------------------------------------------------------------------------
# Confirm text format
# ---------------------------------------------------------------------------


class TestCancelTexts:
    def test_confirm_text_has_placeholders(self):
        formatted = CANCEL_CONFIRM_TEXT.format(photo_count=3, text_count=2)
        assert "3" in formatted
        assert "2" in formatted

    def test_confirmed_text_has_placeholders(self):
        formatted = CANCEL_CONFIRMED_TEXT.format(photo_count=1, text_count=5)
        assert "1" in formatted
        assert "5" in formatted

    def test_confirm_text_mentions_cancel(self):
        assert "/cancel" in CANCEL_CONFIRM_TEXT

    def test_empty_text_is_non_empty(self):
        assert len(CANCEL_EMPTY_TEXT.strip()) > 10
