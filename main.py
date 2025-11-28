import asyncio

from main_app.core.logger import logger
from main_app.infrastructure.bot_factory import dp, bot
from main_app.infrastructure.rabbit_connector import broker


async def main():
    logger.info("Bot service starting...")
    async with broker:
        await broker.start()
        logger.info("Broker started, starting polling")
        await dp.start_polling(bot)
    logger.info("Bot service stopped")


if __name__ == "__main__":
    asyncio.run(main())
