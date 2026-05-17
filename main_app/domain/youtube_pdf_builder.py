"""
main_app/domain/youtube_pdf_builder.py

Строит PdfOrder для очереди pdf.generate из YouTube транскрипта и метаданных.

Место: domain/ — чистая бизнес-логика.
Не знает ни про Telegram, ни про broker, ни про storage.
Принимает данные → возвращает dict для broker.publish().

Структура PDF:
    [ЗАГОЛОВОК ВИДЕО]            ← heading, только если есть title
    Канал · Дата · Длительность  ← paragraph, только заполненные части
    ────────────────────────────
    [транскрипт]
    Источник: https://...        ← если есть url
"""
from typing import Optional

from pdfnik_contracts.pdf_content import (
    PdfHeadingBlock,
    PdfOrder,
    PdfParagraphBlock,
    PdfRichText,
    PdfTextBlock,
)


def _duration_str(duration_sec: Optional[float]) -> str:
    if not duration_sec:
        return ""
    total = int(duration_sec)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _date_str(upload_date: Optional[str]) -> str:
    """'20240315' → '15.03.2024'."""
    d = upload_date
    if not d or len(d) != 8:
        return ""
    return f"{d[6:8]}.{d[4:6]}.{d[:4]}"


def _subtitle_line(meta: dict) -> str:
    """Формирует строку: 'Канал · 15.03.2024 · 12:34'. Пустые части пропускаются."""
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
        metadata: Optional[dict] = None,
) -> dict:
    """
    Строит payload для очереди pdf.generate.

    Аргументы:
        chat_id         — Telegram chat_id для доставки готового PDF
        transcript_text — текст транскрипта (уже декодированный, stripped)
        metadata        — dict из поля youtube_metadata в TxtDoneSuccess,
                          или None если метаданных нет

    Возвращает dict — результат PdfOrder.model_dump(),
    готовый для broker.publish(..., queue="pdf.generate").
    """
    meta = metadata or {}
    blocks = []

    # ── Заголовок ──────────────────────────────────────────────────────────
    title = meta.get("title")
    if title:
        blocks.append(
            PdfHeadingBlock(content=PdfRichText(text=title, entities=[]))
        )

        subtitle = _subtitle_line(meta)
        if subtitle:
            blocks.append(
                PdfParagraphBlock(content=PdfRichText(text=subtitle, entities=[]))
            )

        blocks.append(
            PdfParagraphBlock(content=PdfRichText(text="─" * 40, entities=[]))
        )

    # ── Транскрипт ─────────────────────────────────────────────────────────
    # PdfTextBlock → create_pdf нормализует в параграфы/списки автоматически.
    blocks.append(
        PdfTextBlock(content=PdfRichText(text=transcript_text or "(пустой транскрипт)", entities=[]))
    )

    # ── Ссылка на источник ─────────────────────────────────────────────────
    url = meta.get("url")
    if url:
        blocks.append(
            PdfParagraphBlock(content=PdfRichText(text=f"\nИсточник: {url}", entities=[]))
        )

    return PdfOrder(chat_id=chat_id, items=blocks).model_dump()