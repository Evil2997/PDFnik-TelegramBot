# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/domain/youtube_pdf_builder.py
# repo: PDFnik-TelegramBot

"""
Builds a PdfOrder for the pdf.generate queue from a YouTube transcript and metadata.

Pure domain function — no Telegram, no broker, no storage.
Accepts transcript_text + metadata dict -> returns dict for broker.publish().

PDF structure:
    [VIDEO TITLE]        <- heading, only if title is present
    Channel · Date · Duration  <- paragraph, only populated parts
    ----------------------------------------
    [transcript]
    Source: https://...  <- if url is present
"""

from pdfnik_contracts.pdf_content import (
    PdfHeadingBlock,
    PdfOrder,
    PdfParagraphBlock,
    PdfRichText,
    PdfTextBlock,
)


def _duration_str(duration_sec: float | None) -> str:
    if not duration_sec:
        return ""
    total = int(duration_sec)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _date_str(upload_date: str | None) -> str:
    """Converts '20240315' to '15.03.2024'."""
    d = upload_date
    if not d or len(d) != 8:
        return ""
    return f"{d[6:8]}.{d[4:6]}.{d[:4]}"


def _subtitle_line(meta: dict) -> str:
    """Builds a subtitle line: 'Channel · 15.03.2024 · 12:34'. Empty parts are skipped."""
    parts = []
    if meta.get("channel"):
        parts.append(meta["channel"])
    date = _date_str(meta.get("upload_date"))
    if date:
        parts.append(date)
    duration = _duration_str(meta.get("duration_sec"))
    if duration:
        parts.append(duration)
    return " · ".join(parts)


def build_youtube_pdf_order(
    *,
    chat_id: int,
    transcript_text: str,
    metadata: dict | None = None,
    summary: str | None = None,
) -> dict:
    """
    Builds a payload for the pdf.generate queue.

    Args:
        chat_id         -- Telegram chat_id for PDF delivery
        transcript_text -- decoded and stripped transcript text
        metadata        -- dict from youtube_metadata field in TxtDoneSuccess,
                           or None if metadata is unavailable
        summary         -- LLM-generated summary to insert before the transcript, or None

    Returns a dict (PdfOrder.model_dump()) ready for broker.publish(queue="pdf.generate").
    """
    meta = metadata or {}
    blocks = []

    title = meta.get("title")
    if title:
        blocks.append(PdfHeadingBlock(content=PdfRichText(text=title, entities=[])))

        subtitle = _subtitle_line(meta)
        if subtitle:
            blocks.append(PdfParagraphBlock(content=PdfRichText(text=subtitle, entities=[])))

        blocks.append(PdfParagraphBlock(content=PdfRichText(text="-" * 40, entities=[])))

    if summary:
        blocks.append(PdfHeadingBlock(content=PdfRichText(text="Summary", entities=[])))
        blocks.append(PdfParagraphBlock(content=PdfRichText(text=summary, entities=[])))
        blocks.append(PdfParagraphBlock(content=PdfRichText(text="-" * 40, entities=[])))

    blocks.append(
        PdfTextBlock(content=PdfRichText(text=transcript_text or "(empty transcript)", entities=[]))
    )

    url = meta.get("url")
    if url:
        blocks.append(PdfParagraphBlock(content=PdfRichText(text=f"\nSource: {url}", entities=[])))

    return PdfOrder(chat_id=chat_id, items=blocks).model_dump()  # type: ignore[no-any-return]
