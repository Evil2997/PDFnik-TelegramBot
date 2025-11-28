from aiogram.filters import Command
from aiogram.types import Message

from main_app.application.bot.commands_text import START_TEXT, HELP_TEXT
from main_app.core.logger import logger
from main_app.infrastructure.bot_factory import dp


@dp.message(Command("start"))
async def command_start(msg: Message):
    logger.info(f"/start from chat {msg.chat.id}")
    await msg.answer(START_TEXT)


@dp.message(Command("help"))
async def command_help(msg: Message):
    logger.info(f"/help from chat {msg.chat.id}")
    await msg.answer(HELP_TEXT)
