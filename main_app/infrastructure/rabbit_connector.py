from faststream.rabbit import RabbitBroker

from main_app.core.constants import RABBITMQ_URL

broker = RabbitBroker(RABBITMQ_URL)
