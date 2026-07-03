# repo: PDFnik-TelegramBot

"""
Shared pytest env setup.

Settings() is instantiated at import time in main_app.core.settings and
requires BOT_TOKEN / REDIS_URL / RABBITMQ_URL. Provide dummy defaults so
tests run without manual env exports; real env vars (e.g. in CI) still
take precedence.
"""

import os

os.environ.setdefault("BOT_TOKEN", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost/")  # pragma: allowlist secret
