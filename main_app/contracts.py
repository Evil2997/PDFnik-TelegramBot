from pydantic import BaseModel
from typing import Literal, Union


class TextItem(BaseModel):
    type: Literal["text"]
    text: str


class ImageItem(BaseModel):
    type: Literal["image"]
    filename: str         # имя файла для пользователя (может быть оригинальным)
    storage_key: str      # "images/2025/11/20/uuid.jpg"


Item = Union[TextItem, ImageItem]


class PdfOrder(BaseModel):
    chat_id: int
    items: list[Item]


class BotDocument(BaseModel):
    chat_id: int
    filename: str         # имя PDF для пользователя
    storage_key: str      # "pdf/2025/11/20/uuid.pdf"

# TODO-SHARED-MODELS-001: временная копия контрактов.
# Позже вынести в общий пакет и переиспользовать и в боте, и в pdf-сервисе.
