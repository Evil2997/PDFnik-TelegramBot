"""
spam_guard.py
Telegram-bot side.

Два инструмента:
1. SpamGuard — rate limiting по chat_id через Redis.
2. is_ignorable_message() — фильтр мусорных событий (стикеры, реакции и т.д.)

Использование в хендлерах:
    guard = SpamGuard(redis_client, max_per_minute=10)

    @router.message()
    async def handle_any(message: Message):
        if is_ignorable_message(message):
            return

        if not await guard.allow(message.chat.id):
            await message.answer("⏳ Зачекайте трохи, надто багато запитів.")
            return

        # обработка...
"""
import time
from typing import Optional

from aiogram.types import Message


# ---------------------------------------------------------------------------
# Фильтр мусорных событий
# ---------------------------------------------------------------------------

_IGNORABLE_CONTENT_TYPES = frozenset({
    "sticker",
    "dice",
    "poll",
    "venue",
    "game",
    "story",
})


def is_ignorable_message(message: Message) -> bool:
    """
    Возвращает True если сообщение не требует обработки:
    - стикеры, кубики, опросы, игры, истории
    - service messages (пользователь добавлен/удалён, смена названия чата и т.д.)
    - пустые сообщения без текста, файла, голосового и т.д.

    Хендлер делает early return при True — изолирует сценарии и не засоряет логи.
    """
    # Service messages
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

    # Стикеры и прочий контент без полезной нагрузки
    content_type = getattr(message, "content_type", None)
    if content_type in _IGNORABLE_CONTENT_TYPES:
        return True

    return False


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class SpamGuard:
    """
    Sliding window rate limiter на основе Redis sorted set.

    Алгоритм:
        Для каждого chat_id храним sorted set с timestamp'ами запросов.
        Перед каждым запросом:
        1. Удаляем записи старше window_sec секунд.
        2. Считаем оставшиеся записи.
        3. Если >= max_requests — отказываем.
        4. Иначе — добавляем текущий timestamp и разрешаем.

    Преимущества перед fixed window:
        Нет "двойного burst" на границе окна.
        Точный подсчёт запросов за последние N секунд.
    """

    def __init__(
        self,
        redis,                          # aioredis / redis.asyncio клиент
        *,
        max_requests: int = 10,         # максимум запросов за окно
        window_sec: int = 60,           # размер окна в секундах
        key_prefix: str = "spam:",      # префикс ключей в Redis
        ttl_sec: Optional[int] = None,  # TTL на ключ; по умолчанию window_sec * 2
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
        Проверяет лимит для chat_id.
        Возвращает True если запрос разрешён, False если превышен лимит.
        """
        key = self._key(chat_id)
        now = time.time()
        window_start = now - self._window

        # Используем pipeline для атомарности и минимизации round-trips.
        async with self._redis.pipeline(transaction=True) as pipe:
            # 1. Удаляем устаревшие записи
            pipe.zremrangebyscore(key, "-inf", window_start)
            # 2. Считаем актуальные
            pipe.zcard(key)
            # 3. Добавляем текущий запрос (score = timestamp для уникальности — timestamp + random suffix)
            pipe.zadd(key, {f"{now:.6f}": now})
            # 4. Обновляем TTL
            pipe.expire(key, self._ttl)
            results = await pipe.execute()

        count_before_add = results[1]  # zcard до zadd
        return count_before_add < self._max

    async def remaining(self, chat_id: int) -> int:
        """Сколько запросов ещё разрешено в текущем окне."""
        key = self._key(chat_id)
        now = time.time()
        window_start = now - self._window
        await self._redis.zremrangebyscore(key, "-inf", window_start)
        count = await self._redis.zcard(key)
        return max(0, self._max - count)

    async def reset(self, chat_id: int) -> None:
        """Сбросить счётчик для chat_id (например после /cancel)."""
        await self._redis.delete(self._key(chat_id))