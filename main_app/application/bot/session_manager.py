import asyncio
import time

from aiogram import Bot
from faststream.redis import Redis

# Таймеры, запущенные для каждого чата (локально для процесса).
pause_tasks: dict[int, asyncio.Task] = {}

# Дебаунс для ACK в секундах.
ACK_DEBOUNCE_SEC = 2.0

# Время паузы (тишины) перед отправкой мягкого напоминания, сек.
PAUSE_DURATION_SEC = 10.0

async def ack_user_activity(chat_id: int, bot: Bot, redis: Redis) -> None:
    """
    Отправляет мгновенный ACK «Принял, жду ещё…» один раз в ACK_DEBOUNCE_SEC.
    Хранит timestamp последнего ACK в Redis (`pdf_session:ack_ts:{chat_id}`).
    """
    ts_key = f"pdf_session:ack_ts:{chat_id}"
    now = time.time()

    last_ts = await redis.get(ts_key)
    # Если никогда не отправляли или прошло достаточно времени — отправляем ACK.
    if not last_ts or (now - float(last_ts)) >= ACK_DEBOUNCE_SEC:
        await bot.send_message(chat_id, "Принял, жду ещё…")
        await redis.set(ts_key, str(now))

async def schedule_pause_check(chat_id: int, bot: Bot, redis: Redis) -> None:
    """
    Ставит/перезапускает таймер паузы на PAUSE_DURATION_SEC.
    Версия таймера хранится в Redis (`pdf_session:pause_version:{chat_id}`).
    После сна проверяется версия; если она не изменилась, отправляем напоминание.
    """
    version_key = f"pdf_session:pause_version:{chat_id}"

    # Увеличиваем версию; если ключа нет, INCR создаст его со значением 1.
    version = await redis.incr(version_key)

    # Отменяем существующий локальный таймер для этого чата, если есть.
    current_task = pause_tasks.pop(chat_id, None)
    if current_task:
        current_task.cancel()

    async def _timer(expected_version: int) -> None:
        try:
            await asyncio.sleep(PAUSE_DURATION_SEC)
            # Сравниваем текущую версию с ожидаемой.
            current_version_raw = await redis.get(version_key)
            current_version = int(current_version_raw or 0)
            if current_version == expected_version:
                # Никаких новых сообщений за время паузы
                await bot.send_message(
                    chat_id,
                    "Пока всё понял. Можешь продолжать или напиши /done, когда закончишь."
                )
        except asyncio.CancelledError:
            # Таймер был отменён — ничего не делаем
            return

    # Запускаем новый таймер и сохраняем в словарь для возможной отмены.
    task = asyncio.create_task(_timer(version))
    pause_tasks[chat_id] = task

async def cancel_pause_check(chat_id: int, redis: Redis) -> None:
    """
    Отменяет таймер «тишины» и удаляет версию из Redis.
    Используется при /done, чтобы пауза-сообщение не пришло после завершения.
    """
    version_key = f"pdf_session:pause_version:{chat_id}"
    # Удаляем версию таймера в Redis (считается, что сессия завершена).
    await redis.delete(version_key)

    # Отменяем локальный таймер.
    current_task = pause_tasks.pop(chat_id, None)
    if current_task:
        current_task.cancel()
