# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/session_manager.py
# repo: PDFnik-TelegramBot

import asyncio
import time

from aiogram import Bot
from faststream.redis import Redis
from pydantic import BaseModel, ConfigDict, Field

# Silence duration before sending a soft reminder, seconds.
PAUSE_DURATION_SEC = 15.0


class PauseTaskEntry(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    chat_id: int = Field(
        description=(
            "Telegram chat ID the silence timer is bound to. "
            "Used to uniquely link the timer to a user session."
        )
    )

    version: int = Field(
        description=(
            "Timer generation (version). "
            "Incremented on every new user message. "
            "Used to guard against race conditions: stale timers do not send messages."
        )
    )

    created_at: float = Field(
        default_factory=time.time,
        description=(
            "Unix timestamp when the timer was created. "
            "Used for debugging, diagnostics and future metrics. "
            "Does not affect current business logic."
        ),
    )

    task: asyncio.Task = Field(
        description=(
            "asyncio.Task implementing the silence timer. "
            "After sleeping, checks the version and either sends a reminder "
            "or exits as stale."
        )
    )


class PauseTaskRegistry(BaseModel):
    """
    Timer registry without a plain dict.

    Entries are stored as dynamic model attributes:
      pause_tasks.<chat_id> = PauseTaskEntry(...)
    where <chat_id> is a string key.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def _key(self, chat_id: int) -> str:
        return str(chat_id)

    def get(self, chat_id: int) -> PauseTaskEntry | None:
        return getattr(self, self._key(chat_id), None)

    def set(self, entry: PauseTaskEntry) -> None:
        setattr(self, self._key(entry.chat_id), entry)

    def pop(self, chat_id: int) -> PauseTaskEntry | None:
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
    Sets or restarts the silence timer for PAUSE_DURATION_SEC.
    Timer version is stored in Redis (pdf_session:pause_version:{chat_id}).
    After sleeping, version is checked; if unchanged, a reminder is sent.
    """
    version_key = f"pdf_session:pause_version:{chat_id}"

    # Increment version; INCR creates the key with value 1 if it does not exist.
    version = await redis.incr(version_key)

    # Cancel the previous timer.
    pause_tasks.cancel(chat_id)

    async def _timer(expected_version: int) -> None:
        try:
            await asyncio.sleep(PAUSE_DURATION_SEC)

            current_raw = await redis.get(version_key)
            current_version = int(current_raw or 0)

            if current_version == expected_version:
                # No new messages during the pause window.
                await bot.send_message(
                    chat_id,
                    "Keep sending or type /done when you're ready.",
                )
        except asyncio.CancelledError:
            return

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
    Cancels the silence timer and removes its version from Redis.
    Called on /done so the reminder is not sent after session completion.
    """
    version_key = f"pdf_session:pause_version:{chat_id}"
    # Remove timer version from Redis — session is considered complete.
    await redis.delete(version_key)
    pause_tasks.cancel(chat_id)
