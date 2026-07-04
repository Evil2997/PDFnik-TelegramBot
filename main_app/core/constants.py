# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/core/constants.py
# repo: PDFnik-TelegramBot

import pathlib
from typing import Final

from main_app.core.settings import settings

MAIN_DIR: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]

BOT_TOKEN = settings.BOT_TOKEN
RABBITMQ_URL = settings.RABBITMQ_URL
REDIS_URL = settings.REDIS_URL

# Root of the file storage.
# Mounted as the files_storage volume in docker-compose.
# mkdir happens in main.py - it must not run at module import time,
# otherwise tests fail with PermissionError on /data_files_storage.
FILES_ROOT: Final[pathlib.Path] = pathlib.Path("/data_files_storage")
