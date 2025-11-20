import asyncio
import logging

import sys

from main_app.main_constants import broker, dp, bot
from main_app import commands, on_user_message, send_pdf  # noqa: F401

async def main():
    async with broker:
        await broker.start()
        logging.info("Broker started")
        await dp.start_polling(bot)
    logging.info("Well done! Good work!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
