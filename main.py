import asyncio
import logging

import sys

from main_app.core.constants import broker, dp, bot


async def main():
    async with broker:
        await broker.start()
        logging.info("Broker started")
        await dp.start_polling(bot)
    logging.info("Well done! Good work!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
