from aiogram import Bot, Dispatcher
from main_app.core.settings import settings

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
