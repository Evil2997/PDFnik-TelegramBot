# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/spam_guard.py
# repo: PDFnik-TelegramBot

import contextlib
import time

from aiogram.types import Message

_IGNORABLE_CONTENT_TYPES = frozenset(
    {
        "sticker",
        "dice",
        "poll",
        "venue",
        "game",
        "story",
    }
)


def is_ignorable_message(message: Message) -> bool:
    """
    Returns True if the message requires no processing:
    - stickers, dice, polls, games, stories
    - service messages (member joined/left, title change, etc.)

    Handlers do an early return on True to isolate scenarios
    and avoid polluting logs.
    """
    if (
        message.new_chat_members
        or message.left_chat_member
        or message.new_chat_title
        or message.new_chat_photo
        or message.delete_chat_photo
        or message.group_chat_created
        or message.supergroup_chat_created
        or message.channel_chat_created
        or message.migrate_to_chat_id
        or message.migrate_from_chat_id
        or message.pinned_message
    ):
        return True

    content_type = getattr(message, "content_type", None)
    if content_type in _IGNORABLE_CONTENT_TYPES:
        return True

    return False


class SpamGuard:
    """
    Sliding window rate limiter backed by Redis sorted sets.

    Algorithm:
        For each chat_id a sorted set stores request timestamps.
        Before each request:
        1. Remove entries older than window_sec seconds.
        2. Count remaining entries.
        3. If count >= max_requests — deny.
        4. Otherwise — add current timestamp and allow.

    Advantages over fixed window:
        No double-burst on window boundary.
        Exact count of requests in the last N seconds.
    """

    def __init__(
        self,
        redis,
        *,
        max_requests: int = 10,
        window_sec: int = 60,
        key_prefix: str = "spam:",
        ttl_sec: int | None = None,
    ):
        self._redis = redis
        self._max = max_requests
        self._window = window_sec
        self._prefix = key_prefix
        self._ttl = ttl_sec or window_sec * 2

    def _key(self, chat_id: int) -> str:
        return f"{self._prefix}{chat_id}"

    async def allow(self, chat_id: int) -> bool:
        """
        Checks the rate limit for chat_id.
        Returns True if the request is allowed, False if the limit is exceeded.
        """
        key = self._key(chat_id)
        now = time.time()
        window_start = now - self._window

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            pipe.zadd(key, {f"{now:.6f}": now})
            pipe.expire(key, self._ttl)
            results = await pipe.execute()

        count_before_add = results[1]
        return count_before_add < self._max

    async def remaining(self, chat_id: int) -> int:
        """Returns how many requests are still allowed in the current window."""
        key = self._key(chat_id)
        now = time.time()
        window_start = now - self._window
        await self._redis.zremrangebyscore(key, "-inf", window_start)
        count = await self._redis.zcard(key)
        return max(0, self._max - count)

    async def reset(self, chat_id: int) -> None:
        """Reset the counter for chat_id (e.g. after /cancel)."""
        with contextlib.suppress(Exception):
            await self._redis.delete(self._key(chat_id))
