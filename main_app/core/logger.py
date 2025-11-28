import logging

SERVICE_NAME = "telegram-bot"


def get_logger(name: str | None = None) -> logging.Logger:
    logger_name = name or SERVICE_NAME
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        return logger  # уже настроен

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False
    return logger


# логгер по умолчанию для всего бота
logger = get_logger()
