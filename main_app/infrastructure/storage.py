import datetime as dt
import pathlib
import uuid
from typing import Optional

from pydantic import BaseModel

from main_app.core.constants import FILES_ROOT


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
    Простое файловое хранилище S3-подобного вида.
    TODO: заменить на S3FileStorage, когда появится реальный S3-бакет.
    root — корневая директория, внутри которой будут создаваться подпапки.
    """

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    async def save_bytes(
        self,
        data: bytes,
        *,
        prefix: str,                # "images" / "pdf"
        filename: str,              # оригинальное имя, для пользователя
        content_type: str | None = None,
    ) -> StoredFile:
        # Дата для шардинга (timezone-aware datetime в UTC)
        today = dt.datetime.now(dt.UTC)
        date_prefix = today.strftime("%Y/%m/%d")

        ext = pathlib.Path(filename).suffix  # .jpg, .png, .pdf
        if not ext:
            raise ValueError("Filename must have an extension")

        # Уникальное имя файла внутри хранилища
        unique_name = f"{uuid.uuid4().hex}{ext}"

        storage_key = str(pathlib.Path(prefix) / date_prefix / unique_name)
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

# Локальное хранилище, потом можно будет заменить на S3FileStorage.
storage = LocalFileStorage(FILES_ROOT)
