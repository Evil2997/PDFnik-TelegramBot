from main_app.infrastructure.bot_factory import dp, bot
from main_app.infrastructure.rabbit_connector import broker
from main_app.infrastructure.redis_connector import redis
from main_app.infrastructure.storage import storage

from main_app.application.bot.commands import register_command_handlers
from main_app.application.bot.user_message import register_user_message_handlers
from main_app.application.bot.pdf_consumer import register_pdf_send_consumer


def setup_bot_handlers_and_subscribers() -> None:
    register_command_handlers(dp)
    register_user_message_handlers(dp, broker, redis, bot, storage)
    register_pdf_send_consumer(broker, bot, storage)
