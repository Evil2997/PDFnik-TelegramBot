import datetime as dt
import pathlib
import uuid
from typing import Optional

from pydantic import BaseModel


class StoredFile(BaseModel):
    """
    Результат сохранения файла в хранилище.

    storage_key — S3-подобный ключ (images/2025/11/20/uuid.jpg),
    filename    — имя файла для пользователя (оригинальное),
    size        — размер в байтах (по желанию).
    """
    storage_key: str
    filename: str
    content_type: Optional[str] = None
    size: Optional[int] = None


class LocalFileStorage:
    """
    Локальное хранилище, которое ведёт себя как S3:
    мы работаем только с storage_key, а внутри оно маппится на путь на диске.

    TODO: заменить на S3FileStorage, когда появится реальный S3-бакет.
    """

    def __init__(self, root: pathlib.Path):
        self.root = root

    async def save_bytes(
        self,
        data: bytes,
        *,
        prefix: str,          # "images" / "pdf"
        filename: str,        # оригинальное имя, для пользователя
        content_type: str | None = None,
    ) -> StoredFile:
        # Дата для шардинга
        today = dt.datetime.utcnow()
        date_prefix = today.strftime("%Y/%m/%d")

        ext = pathlib.Path(filename).suffix  # .jpg, .png, .pdf
        if not ext:
            raise FileExistsError()

        # Уникальное имя файла внутри хранилища
        unique_name = f"{uuid.uuid4().hex}{ext}"

        storage_key = f"{prefix}/{date_prefix}/{unique_name}"
        full_path = self.root / storage_key

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)

        return StoredFile(
            storage_key=storage_key,
            filename=filename,
            content_type=content_type,
            size=len(data),
        )

    async def read_bytes(self, storage_key: str) -> bytes:
        full_path = self.root / storage_key
        return full_path.read_bytes()

    async def delete(self, storage_key: str) -> None:
        full_path = self.root / storage_key
        try:
            full_path.unlink()
        except FileNotFoundError:
            pass
