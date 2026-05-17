"""
Тесты для SpamGuard и is_ignorable_message.

SpamGuard тестируется с mock Redis pipeline.
is_ignorable_message тестируется с mock Message объектами.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main_app.spam_guard import SpamGuard, is_ignorable_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis_mock(zcard_result: int = 0) -> MagicMock:
    """
    Создаёт mock Redis клиента с pipeline.
    zcard_result — значение которое вернёт zcard (количество записей до нашего zadd).
    """
    pipe = AsyncMock()
    pipe.zremrangebyscore = AsyncMock()
    pipe.zcard = AsyncMock()
    pipe.zadd = AsyncMock()
    pipe.expire = AsyncMock()
    # execute() возвращает [zremrangebyscore_result, zcard_result, zadd_result, expire_result]
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
    """Создаёт минимальный mock Message."""
    msg = MagicMock()
    # По умолчанию все service-поля = None, content_type = "text"
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
    def test_text_message_not_ignored(self):
        msg = _make_message(content_type="text")
        assert is_ignorable_message(msg) is False

    def test_voice_message_not_ignored(self):
        msg = _make_message(content_type="voice")
        assert is_ignorable_message(msg) is False

    def test_photo_not_ignored(self):
        msg = _make_message(content_type="photo")
        assert is_ignorable_message(msg) is False

    def test_sticker_ignored(self):
        msg = _make_message(content_type="sticker")
        assert is_ignorable_message(msg) is True

    def test_dice_ignored(self):
        msg = _make_message(content_type="dice")
        assert is_ignorable_message(msg) is True

    def test_poll_ignored(self):
        msg = _make_message(content_type="poll")
        assert is_ignorable_message(msg) is True

    def test_new_chat_members_ignored(self):
        msg = _make_message(new_chat_members=[MagicMock()])
        assert is_ignorable_message(msg) is True

    def test_left_chat_member_ignored(self):
        msg = _make_message(left_chat_member=MagicMock())
        assert is_ignorable_message(msg) is True

    def test_pinned_message_ignored(self):
        msg = _make_message(pinned_message=MagicMock())
        assert is_ignorable_message(msg) is True

    def test_new_chat_title_ignored(self):
        msg = _make_message(new_chat_title="New Title")
        assert is_ignorable_message(msg) is True


# ---------------------------------------------------------------------------
# SpamGuard.allow
# ---------------------------------------------------------------------------

class TestSpamGuardAllow:
    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        """5 запросов при лимите 10 — разрешаем."""
        redis = _make_redis_mock(zcard_result=5)
        guard = SpamGuard(redis, max_requests=10, window_sec=60)

        result = await guard.allow(chat_id=123)
        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_at_limit(self):
        """10 запросов при лимите 10 — блокируем."""
        redis = _make_redis_mock(zcard_result=10)
        guard = SpamGuard(redis, max_requests=10, window_sec=60)

        result = await guard.allow(chat_id=123)
        assert result is False

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        """Больше лимита — блокируем."""
        redis = _make_redis_mock(zcard_result=15)
        guard = SpamGuard(redis, max_requests=10, window_sec=60)

        result = await guard.allow(chat_id=123)
        assert result is False

    @pytest.mark.asyncio
    async def test_first_request_always_allowed(self):
        """Первый запрос (0 в счётчике) — всегда разрешаем."""
        redis = _make_redis_mock(zcard_result=0)
        guard = SpamGuard(redis, max_requests=1, window_sec=60)

        result = await guard.allow(chat_id=42)
        assert result is True

    @pytest.mark.asyncio
    async def test_pipeline_called_correctly(self):
        """Проверяем что pipeline используется (атомарность)."""
        redis = _make_redis_mock(zcard_result=0)
        guard = SpamGuard(redis, max_requests=10, window_sec=60)

        await guard.allow(chat_id=123)

        redis.pipeline.assert_called_once_with(transaction=True)

    @pytest.mark.asyncio
    async def test_different_chat_ids_independent(self):
        """Разные chat_id — независимые счётчики."""
        redis1 = _make_redis_mock(zcard_result=9)   # у первого 9 — разрешить
        redis2 = _make_redis_mock(zcard_result=10)  # у второго 10 — заблокировать

        guard1 = SpamGuard(redis1, max_requests=10)
        guard2 = SpamGuard(redis2, max_requests=10)

        assert await guard1.allow(chat_id=1) is True
        assert await guard2.allow(chat_id=2) is False


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

    @pytest.mark.asyncio
    async def test_key_format(self):
        redis = _make_redis_mock()
        guard = SpamGuard(redis, key_prefix="test_prefix:")

        await guard.reset(chat_id=42)

        redis.delete.assert_called_once_with("test_prefix:42")