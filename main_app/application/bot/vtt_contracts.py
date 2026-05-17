# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/vtt_contracts.py
# repo: PDFnik-TelegramBot

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["voice", "audio", "video", "youtube"]
DeliveryMode = Literal["text", "document"]
TargetKind = Literal["storage_key", "url"]


class TxtTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TargetKind
    value: str = Field(min_length=1)


class TxtReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: int
    reply_to_message_id: int | None = None


class TxtDelivery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    mode: DeliveryMode


class TxtTranscribeRequest(BaseModel):
    """
    Canonical payload for the txt.transcribe queue.

    Published by the Telegram bot:
    {
      "job_id": "...",
      "target": {"kind": "storage_key" | "url", "value": "..."},
      "reply": {"chat_id": 123, "reply_to_message_id": 456},
      "delivery": {"source_type": "voice", "mode": "text"},
      "cfg": {}
    }
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1)
    target: TxtTarget
    reply: TxtReply
    delivery: TxtDelivery
    cfg: dict[str, Any] | None = None


class TxtDoneSuccess(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    status: Literal["ok"] = "ok"
    txt_storage_key: str

    reply: TxtReply
    delivery: TxtDelivery

    cached: bool | None = None

    # YouTube metadata — populated only when source_type == "youtube".
    # Used by the bot to build a PDF with title, channel and date.
    youtube_metadata: dict | None = None


class TxtDoneError(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    status: Literal["error"] = "error"

    reply: TxtReply | None = None
    delivery: TxtDelivery | None = None

    error: str | None = None
    error_code: str | None = None


def _parse_reply(data: dict) -> TxtReply:
    if isinstance(data.get("reply"), dict):
        return TxtReply.model_validate(data["reply"])
    return TxtReply(
        chat_id=int(data["chat_id"]),
        reply_to_message_id=data.get("reply_to_message_id"),
    )


def _parse_delivery(data: dict) -> TxtDelivery:
    if isinstance(data.get("delivery"), dict):
        return TxtDelivery.model_validate(data["delivery"])

    source_type = data.get("source_type") or data.get("delivery_mode") or "video"
    mode = data.get("mode")

    if not mode:
        mode = "text" if source_type == "voice" else "document"

    return TxtDelivery(source_type=source_type, mode=mode)


def parse_txt_done_message(data: dict) -> TxtDoneSuccess | TxtDoneError:
    """
    Supports both canonical and legacy txt.done payloads.

    Canonical:
        {"job_id": "...", "status": "ok", "txt_storage_key": "...",
         "reply": {...}, "delivery": {...}, "cached": false}

    Legacy field aliases:
        - chat_id / reply_to_message_id
        - source_type / delivery_mode
        - result_storage_key / text_storage_key / storage_key
        - error_message / error
    """
    status = str(data.get("status") or "").strip().lower()

    if status == "error" or "error" in data or "error_message" in data:
        error_text = data.get("error") or data.get("error_message") or "Unknown error"

        reply = None
        if "reply" in data or "chat_id" in data:
            reply = _parse_reply(data)

        delivery = None
        if "delivery" in data or "source_type" in data or "delivery_mode" in data:
            delivery = _parse_delivery(data)

        return TxtDoneError(
            job_id=str(data["job_id"]),
            status="error",
            reply=reply,
            delivery=delivery,
            error=str(error_text),
            error_code=data.get("error_code"),
        )

    txt_storage_key = data.get("txt_storage_key")
    if not txt_storage_key:
        txt_storage_key = (
            data.get("result_storage_key")
            or data.get("text_storage_key")
            or data.get("storage_key")
        )

    normalized = {
        "job_id": str(data["job_id"]),
        "status": "ok",
        "txt_storage_key": txt_storage_key,
        "reply": _parse_reply(data).model_dump(),
        "delivery": _parse_delivery(data).model_dump(),
        "cached": data.get("cached"),
        "youtube_metadata": data.get("youtube_metadata"),
    }
    return TxtDoneSuccess.model_validate(normalized)
