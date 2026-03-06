from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


SourceType = Literal["voice", "audio", "video", "youtube"]


class TxtTranscribeRequest(BaseModel):
    """
    Очередь: txt.transcribe

    Требование:
      - обязательно source_type
      - либо storage_key (tg uploads), либо input_url (youtube)
    """
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="UUID строкой")
    chat_id: int
    reply_to_message_id: Optional[int] = None

    source_type: SourceType

    # Either:
    storage_key: Optional[str] = Field(
        default=None,
        description="Ключ медиа-файла в storage (если пришло из Telegram upload)",
    )
    # Or:
    input_url: Optional[str] = Field(
        default=None,
        description="URL (например YouTube) если источник не Telegram upload",
    )

    # metadata
    filename: str = Field(description="Имя, которое будет использовано воркером/в ответе")
    mime_type: Optional[str] = Field(default=None, description="MIME тип (если есть)")

    language: Optional[str] = Field(default=None, description="Подсказка языка, если есть")
    cfg: Optional[Dict[str, Any]] = Field(default=None, description="Опциональный конфиг воркера")

    @model_validator(mode="after")
    def _validate_input(self) -> "TxtTranscribeRequest":
        has_storage = bool(self.storage_key)
        has_url = bool(self.input_url)
        if has_storage == has_url:
            # either both set or both empty
            raise ValueError("Exactly one of storage_key or input_url must be provided")
        return self


class TxtDoneSuccess(BaseModel):
    """
    Очередь: txt.done (успех)
    """
    model_config = ConfigDict(extra="allow")  # allow: воркер может эволюционировать

    status: Literal["ok"] = "ok"
    job_id: str
    chat_id: int
    reply_to_message_id: Optional[int] = None
    source_type: SourceType

    txt_storage_key: str = Field(description="Ключ txt результата в storage")
    cached: Optional[bool] = Field(default=None, description="Признак cache hit (если воркер отдаёт)")


class TxtDoneError(BaseModel):
    """
    Очередь: txt.done (ошибка)
    """
    model_config = ConfigDict(extra="allow")

    status: Literal["error"] = "error"
    job_id: str
    chat_id: int
    reply_to_message_id: Optional[int] = None
    source_type: Optional[SourceType] = None

    error_message: str = Field(description="Короткое описание ошибки")
    error_code: Optional[str] = Field(default=None, description="Опциональный код ошибки")


def parse_txt_done_message(data: dict) -> TxtDoneSuccess | TxtDoneError:
    """
    Нормализатор для совместимости с MVP-воркером.

    Ожидаем:
      - status: ok|error
      - txt_storage_key (или возможные legacy-ключи)

    Также подтягиваем source_type если воркер прислал иначе/старым полем.
    """
    status = str(data.get("status") or "").lower().strip()

    # Normalize error message field
    if status == "error" or "error_message" in data or "error" in data:
        if "error_message" not in data and "error" in data:
            data = {**data, "error_message": str(data.get("error"))}
        return TxtDoneError.model_validate(data)

    # Success: normalize txt_storage_key
    if "txt_storage_key" not in data:
        if "result_storage_key" in data:
            data = {**data, "txt_storage_key": data["result_storage_key"]}
        elif "text_storage_key" in data:
            data = {**data, "txt_storage_key": data["text_storage_key"]}
        elif "storage_key" in data:
            # some workers might re-use storage_key for output
            data = {**data, "txt_storage_key": data["storage_key"]}

    # Normalize source_type
    if "source_type" not in data:
        if "delivery_mode" in data:
            data = {**data, "source_type": data["delivery_mode"]}

    return TxtDoneSuccess.model_validate(data)