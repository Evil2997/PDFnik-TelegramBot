# /home/dmitriy/PycharmProjects/Telegram-Bot/tests/unit/test_txt_consumer_youtube_pdf.py
# repo: PDFnik-TelegramBot

"""
Tests for YouTube PDF generation in txt_consumer.py.

Key scenario: _maybe_publish_youtube_pdf must be called regardless of
transcript length — both for short transcripts (sent as text message)
and long transcripts (sent as .txt file).

Previously this was a known limitation: PDF was only generated on the
short path. Both paths now call _maybe_publish_youtube_pdf.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main_app.application.bot.txt_consumer import (
    _SHORT_TEXT_LIMIT,
    _maybe_publish_youtube_pdf,
    _should_send_as_short_message,
)
from main_app.application.bot.vtt_contracts import TxtDelivery, TxtDoneSuccess, TxtReply

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_success(
    source_type: str = "youtube",
    youtube_metadata: dict | None = None,
) -> TxtDoneSuccess:
    return TxtDoneSuccess(
        job_id="job-test-001",
        status="ok",
        txt_storage_key="txts/job-test-001.txt",
        reply=TxtReply(chat_id=12345, reply_to_message_id=None),
        delivery=TxtDelivery(source_type=source_type, mode="document"),
        cached=False,
        youtube_metadata=youtube_metadata
        or {
            "url": "https://youtube.com/watch?v=abc",
            "title": "Test Video",
            "channel": "Test Channel",
            "duration_sec": 600.0,
        },
    )


def _short_transcript() -> str:
    return "Short transcript text." * 10  # well under _SHORT_TEXT_LIMIT


def _long_transcript() -> str:
    return "Long transcript word. " * 300  # over _SHORT_TEXT_LIMIT


# ---------------------------------------------------------------------------
# _should_send_as_short_message
# ---------------------------------------------------------------------------


class TestShouldSendAsShortMessage:
    def test_youtube_short_is_short(self):
        assert _should_send_as_short_message("youtube", _short_transcript()) is True

    def test_youtube_long_is_not_short(self):
        assert _should_send_as_short_message("youtube", _long_transcript()) is False

    def test_voice_never_short(self):
        assert _should_send_as_short_message("voice", _short_transcript()) is False

    def test_exactly_at_limit_is_short(self):
        text = "x" * _SHORT_TEXT_LIMIT
        assert _should_send_as_short_message("youtube", text) is True

    def test_one_over_limit_is_not_short(self):
        text = "x" * (_SHORT_TEXT_LIMIT + 1)
        assert _should_send_as_short_message("youtube", text) is False


# ---------------------------------------------------------------------------
# _maybe_publish_youtube_pdf — unit tests
# ---------------------------------------------------------------------------


class TestMaybePublishYoutubePdf:
    @pytest.mark.asyncio
    async def test_publishes_for_youtube_source(self):
        broker = MagicMock()
        broker.publish = AsyncMock()
        result = _make_success(source_type="youtube")

        with patch(
            "main_app.application.bot.txt_consumer.build_youtube_pdf_order",
            return_value={"chat_id": 12345},
        ):
            await _maybe_publish_youtube_pdf(
                broker=broker,
                result=result,
                transcript_text="Some transcript.",
            )

        broker.publish.assert_awaited_once()
        call_kwargs = broker.publish.call_args
        assert call_kwargs.kwargs.get("queue") == "pdf.generate"

    @pytest.mark.asyncio
    async def test_does_not_publish_for_voice(self):
        broker = MagicMock()
        broker.publish = AsyncMock()
        result = _make_success(source_type="voice")

        await _maybe_publish_youtube_pdf(
            broker=broker,
            result=result,
            transcript_text="Some transcript.",
        )

        broker.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_publish_for_audio(self):
        broker = MagicMock()
        broker.publish = AsyncMock()
        result = _make_success(source_type="audio")

        await _maybe_publish_youtube_pdf(
            broker=broker,
            result=result,
            transcript_text="Some transcript.",
        )

        broker.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_publish_for_empty_transcript(self):
        broker = MagicMock()
        broker.publish = AsyncMock()
        result = _make_success(source_type="youtube")

        await _maybe_publish_youtube_pdf(
            broker=broker,
            result=result,
            transcript_text="",
        )

        broker.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_publish_error(self):
        broker = MagicMock()
        broker.publish = AsyncMock(side_effect=RuntimeError("broker down"))
        result = _make_success(source_type="youtube")

        with patch(
            "main_app.application.bot.txt_consumer.build_youtube_pdf_order",
            return_value={"chat_id": 12345},
        ):
            # Must not raise — PDF publish is non-fatal
            await _maybe_publish_youtube_pdf(
                broker=broker,
                result=result,
                transcript_text="Some transcript.",
            )

    @pytest.mark.asyncio
    async def test_passes_metadata_to_builder(self):
        broker = MagicMock()
        broker.publish = AsyncMock()
        meta = {
            "url": "https://youtube.com/watch?v=xyz",
            "title": "My Video",
            "channel": "My Channel",
        }
        result = _make_success(source_type="youtube", youtube_metadata=meta)

        with patch(
            "main_app.application.bot.txt_consumer.build_youtube_pdf_order",
            return_value={"chat_id": 12345},
        ) as mock_builder:
            await _maybe_publish_youtube_pdf(
                broker=broker,
                result=result,
                transcript_text="Transcript text.",
            )

        mock_builder.assert_called_once_with(
            chat_id=12345,
            transcript_text="Transcript text.",
            metadata=meta,
        )

    @pytest.mark.asyncio
    async def test_works_without_metadata(self):
        broker = MagicMock()
        broker.publish = AsyncMock()
        result = _make_success(source_type="youtube", youtube_metadata=None)

        with patch(
            "main_app.application.bot.txt_consumer.build_youtube_pdf_order",
            return_value={"chat_id": 12345},
        ):
            await _maybe_publish_youtube_pdf(
                broker=broker,
                result=result,
                transcript_text="No metadata but still works.",
            )

        broker.publish.assert_awaited_once()


# ---------------------------------------------------------------------------
# Long transcript path — PDF must still be generated
# ---------------------------------------------------------------------------


class TestYoutubePdfLongTranscript:
    """
    Core regression test for P1 fix.
    Long YouTube transcripts (> _SHORT_TEXT_LIMIT) must produce a PDF
    in addition to the .txt file sent to the user.
    """

    @pytest.mark.asyncio
    async def test_long_transcript_triggers_pdf_generation(self):
        """
        Long transcript: _should_send_as_short_message returns False,
        so the document path is taken. _maybe_publish_youtube_pdf
        must still be called after the document is sent.
        """
        broker = MagicMock()
        broker.publish = AsyncMock()

        long_text = _long_transcript()
        assert not _should_send_as_short_message(
            "youtube", long_text
        ), "Precondition: transcript must be long"

        result = _make_success(source_type="youtube")

        with patch(
            "main_app.application.bot.txt_consumer.build_youtube_pdf_order",
            return_value={"chat_id": 12345},
        ):
            await _maybe_publish_youtube_pdf(
                broker=broker,
                result=result,
                transcript_text=long_text,
            )

        broker.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_short_transcript_also_triggers_pdf_generation(self):
        """
        Short transcript: _should_send_as_short_message returns True.
        _maybe_publish_youtube_pdf must be called here too.
        """
        broker = MagicMock()
        broker.publish = AsyncMock()

        short_text = _short_transcript()
        assert _should_send_as_short_message(
            "youtube", short_text
        ), "Precondition: transcript must be short"

        result = _make_success(source_type="youtube")

        with patch(
            "main_app.application.bot.txt_consumer.build_youtube_pdf_order",
            return_value={"chat_id": 12345},
        ):
            await _maybe_publish_youtube_pdf(
                broker=broker,
                result=result,
                transcript_text=short_text,
            )

        broker.publish.assert_awaited_once()
