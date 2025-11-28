import pathlib
from typing import Final

from aiogram import Bot, Dispatcher
from faststream.rabbit import RabbitBroker
from faststream.redis import Redis

from main_app.core.settings import settings
from main_app.infrastructure.storage import LocalFileStorage

MAIN_DIR: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]

BOT_TOKEN = settings.BOT_TOKEN
RABBITMQ_URL = settings.RABBITMQ_URL
REDIS_URL = settings.REDIS_URL

# Корень "почти S3"-хранилища.
# В docker-compose этот путь смонтирован как volume files_storage.
FILES_ROOT: Final[pathlib.Path] = pathlib.Path("/data_files_storage")
FILES_ROOT.mkdir(exist_ok=True)

