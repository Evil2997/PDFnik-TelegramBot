# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/application/bot/vtt_contracts.py
# repo: PDFnik-TelegramBot

from pdfnik_contracts.txt_content import (
    DeliveryMode,
    SourceType,
    TargetKind,
    TxtDelivery,
    TxtDoneResult,
    TxtReply,
    TxtTarget,
    TxtTranscribeJob,
)

__all__ = [
    "DeliveryMode",
    "SourceType",
    "TargetKind",
    "TxtDelivery",
    "TxtDoneResult",
    "TxtReply",
    "TxtTarget",
    "TxtTranscribeJob",
    "parse_txt_done_message",
]


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


def parse_txt_done_message(data: dict) -> TxtDoneResult:
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

    Returns a single TxtDoneResult, discriminated by `status`.
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

        return TxtDoneResult(
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

    return TxtDoneResult(
        job_id=str(data["job_id"]),
        status="ok",
        txt_storage_key=txt_storage_key,
        reply=_parse_reply(data),
        delivery=_parse_delivery(data),
        cached=data.get("cached"),
        youtube_metadata=data.get("youtube_metadata"),
        summary=data.get("summary"),
        extract_mode=data.get("extract_mode"),
    )
