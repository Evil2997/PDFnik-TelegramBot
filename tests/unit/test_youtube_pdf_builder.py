"""
Тесты для youtube_pdf_builder.py (telegram-bot side).

Покрываем:
- YouTubeMetadataDTO: from_dict, duration_str, upload_date_str
- _make_subtitle_line: разные комбинации полей
- build_youtube_pdf_order: с метаданными и без
"""
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub pdfnik_contracts перед импортом builder
# ---------------------------------------------------------------------------

def _setup_contracts_stubs():
    if "pdfnik_contracts" in sys.modules:
        return

    for name in [
        "pdfnik_contracts",
        "pdfnik_contracts.pdf_content",
    ]:
        sys.modules[name] = types.ModuleType(name)

    pc = sys.modules["pdfnik_contracts.pdf_content"]

    class _RT:
        def __init__(self, *, text, entities=None):
            self.text = text
            self.entities = entities or []

    class _PdfTextBlock:
        def __init__(self, *, content):
            self.content = content
            self.type = "text"

    class _PdfHeadingBlock:
        def __init__(self, *, content):
            self.content = content
            self.type = "heading"

    class _PdfParagraphBlock:
        def __init__(self, *, content):
            self.content = content
            self.type = "paragraph"

    class _PdfOrder:
        def __init__(self, *, chat_id, items):
            self.chat_id = chat_id
            self.items = items

        def model_dump(self):
            return {"chat_id": self.chat_id, "items": []}

    pc.PdfRichText = _RT
    pc.PdfTextBlock = _PdfTextBlock
    pc.PdfHeadingBlock = _PdfHeadingBlock
    pc.PdfParagraphBlock = _PdfParagraphBlock
    pc.PdfOrder = _PdfOrder
    pc.PdfBlock = object


_setup_contracts_stubs()

from main_app.youtube_pdf_builder import (
    YouTubeMetadataDTO,
    _make_separator,
    _make_subtitle_line,
    build_youtube_pdf_order,
)


# ---------------------------------------------------------------------------
# YouTubeMetadataDTO
# ---------------------------------------------------------------------------

class TestYouTubeMetadataDTOFromDict:
    def test_full_dict(self):
        d = {
            "url": "https://youtube.com/watch?v=abc",
            "title": "My Video",
            "channel": "My Channel",
            "upload_date": "20240315",
            "duration_sec": 300.0,
        }
        dto = YouTubeMetadataDTO.from_dict(d)
        assert dto.title == "My Video"
        assert dto.channel == "My Channel"
        assert dto.duration_sec == 300.0

    def test_empty_dict_uses_defaults(self):
        dto = YouTubeMetadataDTO.from_dict({})
        assert dto.url == ""
        assert dto.title is None
        assert dto.channel is None

    def test_missing_keys_safe(self):
        dto = YouTubeMetadataDTO.from_dict({"url": "https://x.com"})
        assert dto.url == "https://x.com"
        assert dto.duration_sec is None


class TestYouTubeMetadataDTODurationStr:
    def test_minutes(self):
        dto = YouTubeMetadataDTO(url="u", duration_sec=185)
        assert dto.duration_str == "3:05"

    def test_hours(self):
        dto = YouTubeMetadataDTO(url="u", duration_sec=3723)
        assert dto.duration_str == "1:02:03"

    def test_none(self):
        dto = YouTubeMetadataDTO(url="u", duration_sec=None)
        assert dto.duration_str == ""


class TestYouTubeMetadataDTOUploadDateStr:
    def test_valid(self):
        dto = YouTubeMetadataDTO(url="u", upload_date="20240315")
        assert dto.upload_date_str == "15.03.2024"

    def test_none(self):
        dto = YouTubeMetadataDTO(url="u", upload_date=None)
        assert dto.upload_date_str == ""


# ---------------------------------------------------------------------------
# _make_subtitle_line
# ---------------------------------------------------------------------------

class TestMakeSubtitleLine:
    def _dto(self, **kwargs):
        return YouTubeMetadataDTO(url="u", **kwargs)

    def test_all_parts(self):
        dto = self._dto(channel="Chan", upload_date="20240315", duration_sec=300)
        line = _make_subtitle_line(dto)
        assert "Chan" in line
        assert "15.03.2024" in line
        assert "5:00" in line
        assert " · " in line

    def test_only_channel(self):
        dto = self._dto(channel="Chan")
        assert _make_subtitle_line(dto) == "Chan"

    def test_no_parts(self):
        dto = self._dto()
        assert _make_subtitle_line(dto) == ""

    def test_channel_and_duration(self):
        dto = self._dto(channel="Chan", duration_sec=60)
        line = _make_subtitle_line(dto)
        assert "Chan" in line
        assert "1:00" in line


# ---------------------------------------------------------------------------
# build_youtube_pdf_order
# ---------------------------------------------------------------------------

class TestBuildYoutubePdfOrder:
    def _write_transcript(self, tmp_path: Path, text: str) -> Path:
        p = tmp_path / "transcript.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def test_with_full_metadata(self, tmp_path):
        transcript = self._write_transcript(tmp_path, "This is the transcript text.")
        meta = {
            "url": "https://youtube.com/watch?v=abc",
            "title": "My Video",
            "channel": "My Channel",
            "upload_date": "20240315",
            "duration_sec": 300.0,
        }

        order = build_youtube_pdf_order(
            chat_id=12345,
            transcript_path=transcript,
            metadata_dict=meta,
        )

        assert order.chat_id == 12345
        assert len(order.items) >= 3  # heading + subtitle + separator + transcript + source

        # Первый блок — heading с заголовком
        heading = order.items[0]
        assert heading.type == "heading"
        assert heading.content.text == "My Video"

        # Должен содержать блок с транскриптом
        texts = [b.content.text for b in order.items]
        assert any("transcript text" in t for t in texts)

        # Должен содержать ссылку на источник
        assert any("youtube.com/watch?v=abc" in t for t in texts)

    def test_without_metadata(self, tmp_path):
        transcript = self._write_transcript(tmp_path, "Transcript without metadata.")
        order = build_youtube_pdf_order(
            chat_id=99,
            transcript_path=transcript,
            metadata_dict=None,
        )

        assert order.chat_id == 99
        # Без метаданных — только блок с транскриптом
        assert len(order.items) == 1
        assert "Transcript without metadata" in order.items[0].content.text

    def test_with_title_no_other_metadata(self, tmp_path):
        transcript = self._write_transcript(tmp_path, "Text.")
        meta = {"url": "https://x.com", "title": "Only Title"}

        order = build_youtube_pdf_order(
            chat_id=1,
            transcript_path=transcript,
            metadata_dict=meta,
        )

        heading = order.items[0]
        assert heading.type == "heading"
        assert heading.content.text == "Only Title"

    def test_without_title_no_heading(self, tmp_path):
        """Если title нет — heading не добавляется."""
        transcript = self._write_transcript(tmp_path, "Text.")
        meta = {"url": "https://x.com", "channel": "Chan"}

        order = build_youtube_pdf_order(
            chat_id=1,
            transcript_path=transcript,
            metadata_dict=meta,
        )

        # Нет heading — блоков меньше
        types = [b.type for b in order.items]
        assert "heading" not in types

    def test_transcript_whitespace_stripped(self, tmp_path):
        """Ведущие/хвостовые пробелы в транскрипте обрезаются."""
        transcript = self._write_transcript(tmp_path, "\n\n  Hello world.  \n\n")
        order = build_youtube_pdf_order(chat_id=1, transcript_path=transcript)
        texts = [b.content.text for b in order.items]
        assert any("Hello world." in t for t in texts)

    def test_empty_metadata_dict(self, tmp_path):
        """Пустой dict — не вызывает ошибок, heading не добавляется."""
        transcript = self._write_transcript(tmp_path, "Text.")
        order = build_youtube_pdf_order(
            chat_id=1,
            transcript_path=transcript,
            metadata_dict={},
        )
        types = [b.type for b in order.items]
        assert "heading" not in types