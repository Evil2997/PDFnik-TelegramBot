from pydantic import BaseModel
from typing import Literal, Union


class TextItem(BaseModel):
    type: Literal["text"]
    text: str


class ImageItem(BaseModel):
    type: Literal["image"]
    filename: str
    content_b64: str


Item = Union[TextItem, ImageItem]


class PdfOrder(BaseModel):
    chat_id: int
    items: list[Item]


class BotDocument(BaseModel):
    chat_id: int
    filename: str
    pdf_b64: str

# TODO-SHARED-MODELS-001: временная копия контрактов.
# После вынесения в общий пакет pdfnik-contracts удалить и использовать импорт.
