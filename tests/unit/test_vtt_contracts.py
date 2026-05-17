# /home/dmitriy/PycharmProjects/Telegram-Bot/tests/unit/test_vtt_contracts.py
# repo: PDFnik-TelegramBot

import pytest

from main_app.application.bot.vtt_contracts import (
    TxtDoneError,
    TxtDoneSuccess,
    _parse_delivery,
    _parse_reply,
    parse_txt_done_message,
)


# ---------------------------------------------------------------------------
# _parse_reply
# ---------------------------------------------------------------------------

class TestParseReply:
    def test_canonical_reply_dict(self):
        data = {"reply": {"chat_id": 123, "reply_to_message_id": 456}}
        reply = _parse_reply(data)
        assert reply.chat_id == 123
        assert reply.reply_to_message_id == 456

    def test_legacy_flat_fields(self):
        data = {"chat_id": 789, "reply_to_message_id": None}
        reply = _parse_reply(data)
        assert reply.chat_id == 789
        assert reply.reply_to_message_id is None

    def test_reply_without_reply_to(self):
        data = {"reply": {"chat_id": 100}}
        reply = _parse_reply(data)
        assert reply.chat_id == 100
        assert reply.reply_to_message_id is None


# ---------------------------------------------------------------------------
# _parse_delivery
# ---------------------------------------------------------------------------

class TestParseDelivery:
    def test_canonical_delivery_dict(self):
        data = {"delivery": {"source_type": "youtube", "mode": "document"}}
        delivery = _parse_delivery(data)
        assert delivery.source_type == "youtube"
        assert delivery.mode == "document"

    def test_legacy_source_type_voice(self):
        data = {"source_type": "voice"}
        delivery = _parse_delivery(data)
        assert delivery.source_type == "voice"
        assert delivery.mode == "text"

    def test_legacy_video_default_mode(self):
        data = {"source_type": "video"}
        delivery = _parse_delivery(data)
        assert delivery.mode == "document"

    def test_missing_source_defaults_to_video(self):
        data = {}
        delivery = _parse_delivery(data)
        assert delivery.source_type == "video"


# ---------------------------------------------------------------------------
# parse_txt_done_message — success
# ---------------------------------------------------------------------------

class TestParseTxtDoneSuccess:
    def _ok(self, **kwargs) -> dict:
        base = {
            "job_id": "job-abc",
            "status": "ok",
            "txt_storage_key": "txts/job-abc.txt",
            "reply": {"chat_id": 111, "reply_to_message_id": 222},
            "delivery": {"source_type": "youtube", "mode": "document"},
            "cached": False,
        }
        base.update(kwargs)
        return base

    def test_canonical_success(self):
        result = parse_txt_done_message(self._ok())
        assert isinstance(result, TxtDoneSuccess)
        assert result.job_id == "job-abc"
        assert result.txt_storage_key == "txts/job-abc.txt"
        assert result.reply.chat_id == 111
        assert result.delivery.source_type == "youtube"

    def test_youtube_metadata_passed_through(self):
        meta = {"url": "https://youtube.com/watch?v=abc", "title": "Test", "duration_sec": 300.0}
        result = parse_txt_done_message(self._ok(youtube_metadata=meta))
        assert isinstance(result, TxtDoneSuccess)
        assert result.youtube_metadata is not None
        assert result.youtube_metadata["title"] == "Test"

    def test_no_youtube_metadata_is_none(self):
        result = parse_txt_done_message(self._ok())
        assert isinstance(result, TxtDoneSuccess)
        assert result.youtube_metadata is None

    def test_cached_field_preserved(self):
        result = parse_txt_done_message(self._ok(cached=True))
        assert isinstance(result, TxtDoneSuccess)
        assert result.cached is True

    def test_legacy_result_storage_key(self):
        data = {
            "job_id": "j1", "status": "ok",
            "result_storage_key": "txts/legacy.txt",
            "reply": {"chat_id": 1},
            "delivery": {"source_type": "voice", "mode": "text"},
        }
        result = parse_txt_done_message(data)
        assert isinstance(result, TxtDoneSuccess)
        assert result.txt_storage_key == "txts/legacy.txt"


# ---------------------------------------------------------------------------
# parse_txt_done_message — error
# ---------------------------------------------------------------------------

class TestParseTxtDoneError:
    def _err(self, **kwargs) -> dict:
        base = {
            "job_id": "job-err",
            "status": "error",
            "error": "Transcription failed",
            "reply": {"chat_id": 333},
            "delivery": {"source_type": "voice", "mode": "text"},
        }
        base.update(kwargs)
        return base

    def test_canonical_error(self):
        result = parse_txt_done_message(self._err())
        assert isinstance(result, TxtDoneError)
        assert result.error == "Transcription failed"

    def test_error_code_preserved(self):
        result = parse_txt_done_message(self._err(error_code="WHISPER_OOM"))
        assert isinstance(result, TxtDoneError)
        assert result.error_code == "WHISPER_OOM"

    def test_error_without_reply(self):
        data = {"job_id": "j3", "status": "error", "error": "oops"}
        result = parse_txt_done_message(data)
        assert isinstance(result, TxtDoneError)
        assert result.reply is None

    def test_error_key_without_status_field(self):
        data = {"job_id": "j5", "error": "something went wrong", "chat_id": 1}
        result = parse_txt_done_message(data)
        assert isinstance(result, TxtDoneError)