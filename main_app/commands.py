from aiogram.filters import Command
from aiogram.types import Message

from main_app.main_constants import dp
from main_app.text import START_TEXT, HELP_TEXT


@dp.message(Command("start"))
async def command_start(msg: Message):
    await msg.answer(START_TEXT)


@dp.message(Command("help"))
async def command_help(msg: Message):
    await msg.answer(HELP_TEXT)
