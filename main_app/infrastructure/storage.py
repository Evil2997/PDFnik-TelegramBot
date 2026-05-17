# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/infrastructure/storage.py
# repo: PDFnik-TelegramBot

import contextlib
import datetime as dt
import pathlib
import uuid

from pydantic import BaseModel

from main_app.core.constants import FILES_ROOT


class StoredFile(BaseModel):
    """
    Result of saving a file to storage.

    storage_key -- S3-style key (images/2025/11/20/uuid.jpg)
    filename    -- original filename shown to the user
    size        -- size in bytes (optional)
    """

    storage_key: str
    filename: str
    content_type: str | None = None
    size: int | None = None


class LocalFileStorage:
    """
    Simple S3-style local file storage.
    TODO: replace with S3FileStorage when a real S3 bucket is available.
    """

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        # mkdir is intentionally not called here.
        # Calling mkdir at instantiation caused PermissionError in test environments
        # where the Docker volume is not mounted at /data_files_storage.
        # Directory is created lazily in save_bytes on first actual write.

    async def save_bytes(
        self,
        data: bytes,
        *,
        prefix: str,
        filename: str,
        content_type: str | None = None,
    ) -> StoredFile:
        today = dt.datetime.now(dt.UTC)
        date_prefix = today.strftime("%Y/%m/%d")

        ext = pathlib.Path(filename).suffix
        if not ext:
            raise ValueError("Filename must have an extension")

        unique_name = f"{uuid.uuid4().hex}{ext}"
        storage_key = str(pathlib.Path(prefix) / date_prefix / unique_name)
        full_path = self.root / storage_key

        # Create directory on first write only.
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
        with contextlib.suppress(FileNotFoundError):
            full_path.unlink()


# Module-level singleton.
# LocalFileStorage(FILES_ROOT) is safe to instantiate here —
# mkdir is called lazily in save_bytes, not in __init__.
storage = LocalFileStorage(FILES_ROOT)
