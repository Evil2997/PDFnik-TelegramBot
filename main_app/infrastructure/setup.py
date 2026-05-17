from main_app.application.bot.commands import register_command_handlers
from main_app.application.bot.pdf_consumer import register_pdf_send_consumer
from main_app.application.bot.txt_consumer import register_txt_done_consumer
from main_app.application.bot.user_message import register_user_message_handlers
from main_app.application.bot.vtt_message import register_vtt_message_handlers
from main_app.infrastructure.bot_factory import bot, dp
from main_app.infrastructure.rabbit_connector import broker
from main_app.infrastructure.redis_connector import redis
from main_app.infrastructure.storage import storage


def setup_bot_handlers_and_subscribers() -> None:
    # commands first
    register_command_handlers(dp)

    # VTT ingress should be registered BEFORE generic text handler,
    # so YouTube links can be intercepted without breaking existing text/photo logic.
    register_vtt_message_handlers(dp, bot, storage, broker, redis)

    # existing user text/photo session logic (PDF is built only from this)
    register_user_message_handlers(dp, redis, bot, storage)

    # existing PDF pipeline
    register_pdf_send_consumer(broker, bot, storage)

    # VTT egress
    register_txt_done_consumer(broker, bot, storage)
