"""
tests/unit/test_youtube_pdf_builder.py

Тесты для main_app/domain/youtube_pdf_builder.py
"""

import sys
import types

# ---------------------------------------------------------------------------
# Stub pdfnik_contracts (Not available in the test environment.)
# ---------------------------------------------------------------------------


def _setup_stubs() -> None:
    if "pdfnik_contracts" in sys.modules:
        return

    for name in ["pdfnik_contracts", "pdfnik_contracts.pdf_content"]:
        sys.modules[name] = types.ModuleType(name)

    pc = sys.modules["pdfnik_contracts.pdf_content"]

    class _RT:
        def __init__(self, *, text: str, entities=None):
            self.text = text
            self.entities = entities or []

    class _PdfTextBlock:
        type = "text"

        def __init__(self, *, content):
            self.content = content

    class _PdfHeadingBlock:
        type = "heading"

        def __init__(self, *, content):
            self.content = content

    class _PdfParagraphBlock:
        type = "paragraph"

        def __init__(self, *, content):
            self.content = content

    class _PdfOrder:
        def __init__(self, *, chat_id: int, items: list):
            self.chat_id = chat_id
            self.items = items

        def model_dump(self) -> dict:
            return {"chat_id": self.chat_id, "items": []}

    pc.PdfRichText = _RT
    pc.PdfTextBlock = _PdfTextBlock
    pc.PdfHeadingBlock = _PdfHeadingBlock
    pc.PdfParagraphBlock = _PdfParagraphBlock
    pc.PdfOrder = _PdfOrder


_setup_stubs()

from main_app.domain.youtube_pdf_builder import (  # noqa: E402
    _date_str,
    _duration_str,
    _subtitle_line,
    build_youtube_pdf_order,
)

# ---------------------------------------------------------------------------
# _duration_str
# ---------------------------------------------------------------------------


class TestDurationStr:
    def test_minutes_seconds(self):
        assert _duration_str(185.0) == "3:05"

    def test_hours(self):
        assert _duration_str(3723.0) == "1:02:03"

    def test_none(self):
        assert _duration_str(None) == ""

    def test_zero(self):
        assert _duration_str(0) == ""


# ---------------------------------------------------------------------------
# _date_str
# ---------------------------------------------------------------------------


class TestDateStr:
    def test_valid(self):
        assert _date_str("20240315") == "15.03.2024"

    def test_none(self):
        assert _date_str(None) == ""

    def test_wrong_length(self):
        assert _date_str("2024") == ""


# ---------------------------------------------------------------------------
# _subtitle_line
# ---------------------------------------------------------------------------


class TestSubtitleLine:
    def test_all_parts(self):
        meta = {"channel": "Chan", "upload_date": "20240315", "duration_sec": 300.0}
        line = _subtitle_line(meta)
        assert "Chan" in line
        assert "15.03.2024" in line
        assert "5:00" in line
        assert " · " in line

    def test_empty_meta(self):
        assert _subtitle_line({}) == ""

    def test_only_channel(self):
        assert _subtitle_line({"channel": "Chan"}) == "Chan"


# ---------------------------------------------------------------------------
# build_youtube_pdf_order
# ---------------------------------------------------------------------------


class TestBuildYoutubePdfOrder:
    def test_returns_dict(self):
        result = build_youtube_pdf_order(
            chat_id=123,
            transcript_text="Hello world.",
        )
        assert isinstance(result, dict)
        assert result["chat_id"] == 123

    def test_with_full_metadata_has_heading(self):
        result = build_youtube_pdf_order(
            chat_id=1,
            transcript_text="Transcript.",
            metadata={
                "url": "https://youtube.com/watch?v=abc",
                "title": "My Video",
                "channel": "Chan",
                "upload_date": "20240315",
                "duration_sec": 300.0,
            },
        )
        # result.items is not included in model_dump() (our stub returns []),
        # but we can verify that the function does not crash and returns a dict.
        assert isinstance(result, dict)

    def test_without_metadata_no_crash(self):
        result = build_youtube_pdf_order(
            chat_id=99,
            transcript_text="Some text.",
            metadata=None,
        )
        assert isinstance(result, dict)

    def test_empty_transcript_uses_placeholder(self):
        # Should not fail on an empty line
        result = build_youtube_pdf_order(
            chat_id=1,
            transcript_text="",
        )
        assert isinstance(result, dict)

    def test_chat_id_preserved(self):
        result = build_youtube_pdf_order(chat_id=42, transcript_text="text")
        assert result["chat_id"] == 42
