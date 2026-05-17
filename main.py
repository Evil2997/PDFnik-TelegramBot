# /home/dmitriy/PycharmProjects/Telegram-Bot/main.py
# repo: PDFnik-TelegramBot

import asyncio

from main_app.core.constants import FILES_ROOT
from main_app.core.logger import logger
from main_app.infrastructure.bot_factory import dp, bot
from main_app.infrastructure.rabbit_connector import broker
from main_app.infrastructure.setup import setup_bot_handlers_and_subscribers


async def main():
    FILES_ROOT.mkdir(parents=True, exist_ok=True)

    setup_bot_handlers_and_subscribers()
    logger.info("Bot service starting...")
    async with broker:
        await broker.start()
        logger.info("Broker started, starting polling")
        await dp.start_polling(bot)
    logger.info("Bot service stopped")


if __name__ == "__main__":
    asyncio.run(main())