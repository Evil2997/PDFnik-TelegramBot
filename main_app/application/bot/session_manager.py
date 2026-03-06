import asyncio
import time
from typing import Optional

from aiogram import Bot
from faststream.redis import Redis
from pydantic import BaseModel, ConfigDict, Field

# Время паузы (тишины) перед отправкой мягкого напоминания, сек.
PAUSE_DURATION_SEC = 15.0


class PauseTaskEntry(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    chat_id: int = Field(
        description=(
            "Telegram chat ID, к которому привязан таймер тишины. "
            "Используется для однозначной связи таймера с пользовательской сессией."
        )
    )

    version: int = Field(
        description=(
            "Версия (поколение) таймера тишины. "
            "Инкрементируется при каждом новом сообщении пользователя и используется "
            "для защиты от race conditions: устаревшие таймеры не отправляют сообщения."
        )
    )

    created_at: float = Field(
        default_factory=time.time,
        description=(
            "Unix-timestamp момента создания таймера. "
            "Нужен для отладки, диагностики и возможных будущих метрик. "
            "На текущую бизнес-логику не влияет."
        ),
    )

    task: asyncio.Task = Field(
        description=(
            "Асинхронная asyncio.Task, реализующая таймер тишины. "
            "После ожидания проверяет version и либо отправляет сообщение о паузе, "
            "либо завершается как устаревшая."
        )
    )


class PauseTaskRegistry(BaseModel):
    """
    Реестр таймеров БЕЗ dict/dict.

    Храним записи как динамические атрибуты модели:
      pause_tasks.<chat_id> = PauseTaskEntry(...)
    Где <chat_id> — строка.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def _key(self, chat_id: int) -> str:
        return str(chat_id)

    def get(self, chat_id: int) -> Optional[PauseTaskEntry]:
        return getattr(self, self._key(chat_id), None)

    def set(self, entry: PauseTaskEntry) -> None:
        setattr(self, self._key(entry.chat_id), entry)

    def pop(self, chat_id: int) -> Optional[PauseTaskEntry]:
        key = self._key(chat_id)
        entry = getattr(self, key, None)
        if entry is not None:
            delattr(self, key)
        return entry

    def cancel(self, chat_id: int) -> None:
        entry = self.pop(chat_id)
        if entry and entry.task:
            entry.task.cancel()


pause_tasks = PauseTaskRegistry()


async def schedule_pause_check(chat_id: int, bot: Bot, redis: Redis) -> None:
    """
    Ставит/перезапускает таймер паузы на PAUSE_DURATION_SEC.
    Версия таймера хранится в Redis (`pdf_session:pause_version:{chat_id}`).
    После сна проверяется версия; если она не изменилась, отправляем напоминание.
    """
    version_key = f"pdf_session:pause_version:{chat_id}"

    # Увеличиваем версию; если ключа нет, INCR создаст его со значением 1.
    version = await redis.incr(version_key)

    # отменяем предыдущий таймер
    pause_tasks.cancel(chat_id)

    async def _timer(expected_version: int) -> None:
        try:
            await asyncio.sleep(PAUSE_DURATION_SEC)

            current_raw = await redis.get(version_key)
            current_version = int(current_raw or 0)

            if current_version == expected_version:
                # Никаких новых сообщений за время паузы
                await bot.send_message(
                    chat_id,
                    "Продолжайте или напишите /done, когда все будет готово.",
                )
        except asyncio.CancelledError:
            # Таймер был отменён — ничего не делаем
            return

    # Запускаем новый таймер и сохраняем в словарь для возможной отмены.
    task = asyncio.create_task(_timer(version))
    pause_tasks.set(
        PauseTaskEntry(
            chat_id=chat_id,
            version=version,
            task=task,
        )
    )


async def cancel_pause_check(chat_id: int, redis: Redis) -> None:
    """
    Отменяет таймер «тишины» и удаляет версию из Redis.
    Используется при /done, чтобы пауза-сообщение не пришло после завершения.
    """
    version_key = f"pdf_session:pause_version:{chat_id}"
    # Удаляем версию таймера в Redis (считается, что сессия завершена).
    await redis.delete(version_key)

    pause_tasks.cancel(chat_id)
