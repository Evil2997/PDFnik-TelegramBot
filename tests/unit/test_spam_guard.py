# /home/dmitriy/PycharmProjects/Telegram-Bot/tests/unit/test_spam_guard.py
# repo: PDFnik-TelegramBot

"""
Тесты для SpamGuard и is_ignorable_message.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from main_app.application.bot.spam_guard import SpamGuard, is_ignorable_message

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock(zcard_result: int = 0) -> MagicMock:
    pipe = AsyncMock()
    pipe.zremrangebyscore = AsyncMock()
    pipe.zcard = AsyncMock()
    pipe.zadd = AsyncMock()
    pipe.expire = AsyncMock()
    pipe.execute = AsyncMock(return_value=[0, zcard_result, 1, True])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)

    redis = AsyncMock()
    redis.pipeline = MagicMock(return_value=pipe)
    redis.zremrangebyscore = AsyncMock()
    redis.zcard = AsyncMock(return_value=zcard_result)
    redis.delete = AsyncMock()
    return redis


def _make_message(**kwargs) -> MagicMock:
    msg = MagicMock()
    defaults = {
        "new_chat_members": None,
        "left_chat_member": None,
        "new_chat_title": None,
        "new_chat_photo": None,
        "delete_chat_photo": None,
        "group_chat_created": None,
        "supergroup_chat_created": None,
        "channel_chat_created": None,
        "migrate_to_chat_id": None,
        "migrate_from_chat_id": None,
        "pinned_message": None,
        "content_type": "text",
    }
    defaults.update(kwargs)
    for key, value in defaults.items():
        setattr(msg, key, value)
    return msg


# ---------------------------------------------------------------------------
# is_ignorable_message
# ---------------------------------------------------------------------------


class TestIsIgnorableMessage:
    def test_text_not_ignored(self):
        assert is_ignorable_message(_make_message(content_type="text")) is False

    def test_voice_not_ignored(self):
        assert is_ignorable_message(_make_message(content_type="voice")) is False

    def test_photo_not_ignored(self):
        assert is_ignorable_message(_make_message(content_type="photo")) is False

    def test_sticker_ignored(self):
        assert is_ignorable_message(_make_message(content_type="sticker")) is True

    def test_dice_ignored(self):
        assert is_ignorable_message(_make_message(content_type="dice")) is True

    def test_poll_ignored(self):
        assert is_ignorable_message(_make_message(content_type="poll")) is True

    def test_new_chat_members_ignored(self):
        assert is_ignorable_message(_make_message(new_chat_members=[MagicMock()])) is True

    def test_left_chat_member_ignored(self):
        assert is_ignorable_message(_make_message(left_chat_member=MagicMock())) is True

    def test_pinned_message_ignored(self):
        assert is_ignorable_message(_make_message(pinned_message=MagicMock())) is True


# ---------------------------------------------------------------------------
# SpamGuard.allow
# ---------------------------------------------------------------------------


class TestSpamGuardAllow:
    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        guard = SpamGuard(_make_redis_mock(zcard_result=5), max_requests=10)
        assert await guard.allow(chat_id=123) is True

    @pytest.mark.asyncio
    async def test_blocks_at_limit(self):
        guard = SpamGuard(_make_redis_mock(zcard_result=10), max_requests=10)
        assert await guard.allow(chat_id=123) is False

    @pytest.mark.asyncio
    async def test_first_request_always_allowed(self):
        guard = SpamGuard(_make_redis_mock(zcard_result=0), max_requests=1)
        assert await guard.allow(chat_id=42) is True

    @pytest.mark.asyncio
    async def test_pipeline_used(self):
        redis = _make_redis_mock(zcard_result=0)
        guard = SpamGuard(redis, max_requests=10)
        await guard.allow(chat_id=123)
        redis.pipeline.assert_called_once_with(transaction=True)


# ---------------------------------------------------------------------------
# SpamGuard.reset
# ---------------------------------------------------------------------------


class TestSpamGuardReset:
    @pytest.mark.asyncio
    async def test_reset_calls_delete(self):
        redis = _make_redis_mock()
        guard = SpamGuard(redis, key_prefix="spam:")
        await guard.reset(chat_id=999)
        redis.delete.assert_called_once_with("spam:999")
