# /home/dmitriy/PycharmProjects/Telegram-Bot/tests/unit/test_txt_consumer_delivery.py
# repo: PDFnik-TelegramBot


from main_app.application.bot.txt_consumer import (
    _SHORT_TEXT_LIMIT,
    _VOICE_MAX_TEXT_CHUNKS,
    _chunk_text,
    _reply_kwargs,
    _should_send_as_short_message,
    _target_kind_from_source_type,
)

# ---------------------------------------------------------------------------
# _reply_kwargs
# ---------------------------------------------------------------------------


class TestReplyKwargs:
    def test_with_id(self):
        assert _reply_kwargs(42) == {"reply_to_message_id": 42}

    def test_none_returns_empty(self):
        assert _reply_kwargs(None) == {}

    def test_zero_returns_empty(self):
        assert _reply_kwargs(0) == {}


# ---------------------------------------------------------------------------
# _target_kind_from_source_type
# ---------------------------------------------------------------------------


class TestTargetKind:
    def test_youtube_is_url(self):
        assert _target_kind_from_source_type("youtube") == "url"

    def test_voice_is_storage_key(self):
        assert _target_kind_from_source_type("voice") == "storage_key"

    def test_audio_is_storage_key(self):
        assert _target_kind_from_source_type("audio") == "storage_key"

    def test_video_is_storage_key(self):
        assert _target_kind_from_source_type("video") == "storage_key"

    def test_none_is_storage_key(self):
        assert _target_kind_from_source_type(None) == "storage_key"


# ---------------------------------------------------------------------------
# _should_send_as_short_message
# ---------------------------------------------------------------------------


class TestShouldSendAsShortMessage:
    def _short(self) -> str:
        return "x" * (_SHORT_TEXT_LIMIT - 1)

    def _long(self) -> str:
        return "x" * (_SHORT_TEXT_LIMIT + 1)

    def test_youtube_short(self):
        assert _should_send_as_short_message("youtube", self._short()) is True

    def test_youtube_long(self):
        assert _should_send_as_short_message("youtube", self._long()) is False

    def test_video_short(self):
        assert _should_send_as_short_message("video", self._short()) is True

    def test_audio_short(self):
        assert _should_send_as_short_message("audio", self._short()) is True

    def test_voice_always_false(self):
        assert _should_send_as_short_message("voice", self._short()) is False
        assert _should_send_as_short_message("voice", self._long()) is False

    def test_exactly_at_limit(self):
        assert _should_send_as_short_message("youtube", "x" * _SHORT_TEXT_LIMIT) is True

    def test_one_over_limit(self):
        assert _should_send_as_short_message("youtube", "x" * (_SHORT_TEXT_LIMIT + 1)) is False


# ---------------------------------------------------------------------------
# _chunk_text
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_empty_returns_one_empty_string(self):
        assert _chunk_text("") == [""]

    def test_short_text_one_chunk(self):
        chunks = _chunk_text("hello")
        assert len(chunks) == 1
        assert chunks[0] == "hello"

    def test_long_text_splits(self):
        chunks = _chunk_text("a" * (_SHORT_TEXT_LIMIT * 2 + 100))
        assert len(chunks) > 1

    def test_all_chunks_within_telegram_limit(self):
        chunks = _chunk_text("b" * (_SHORT_TEXT_LIMIT * 5))
        for chunk in chunks:
            assert len(chunk) <= 4096

    def test_content_preserved(self):
        text = "abc" * 2000
        assert "".join(_chunk_text(text)) == text

    def test_over_voice_max_chunks(self):
        text = "x" * (_SHORT_TEXT_LIMIT * (_VOICE_MAX_TEXT_CHUNKS + 1))
        chunks = _chunk_text(text)
        assert len(chunks) > _VOICE_MAX_TEXT_CHUNKS
