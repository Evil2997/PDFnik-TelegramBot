from aiogram import Bot, Dispatcher
from faststream.rabbit import RabbitBroker
from faststream.redis import Redis

from main_app.settings import settings

BOT_TOKEN = settings.BOT_TOKEN
RABBITMQ_URL = settings.RABBITMQ_URL
REDIS_URL = settings.REDIS_URL

redis = Redis.from_url(REDIS_URL)
broker = RabbitBroker(RABBITMQ_URL)

dp = Dispatcher()

bot = Bot(token=BOT_TOKEN)
