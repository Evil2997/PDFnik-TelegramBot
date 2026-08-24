"""
Tests for the Telegram download-size guard in vtt_message.

Telegram's cloud Bot API refuses getFile for anything over 20 MB. Before the
guard existed the bot tried the download anyway, got TelegramBadRequest, and
answered "Could not download file from Telegram. Please try again." - advice
that can never work, because the limit is a platform cap rather than a
transient failure.
"""

from types import SimpleNamespace

import pytest

from main_app.application.bot.vtt_message import (
    _BYTES_PER_MB,
    _TELEGRAM_MAX_DOWNLOAD_BYTES,
    _media_file,
    _oversized_file_bytes,
)


def _msg(**attachments: object) -> SimpleNamespace:
    """Message stub carrying only the attachment slots vtt_message reads."""
    slots = {"voice": None, "audio": None, "video": None, "document": None}
    slots.update(attachments)
    return SimpleNamespace(**slots)


def _file(size: int | None) -> SimpleNamespace:
    return SimpleNamespace(file_size=size)


class TestMediaFile:
    @pytest.mark.parametrize("slot", ["voice", "audio", "video", "document"])
    def test_returns_the_attachment_in_any_slot(self, slot: str) -> None:
        attachment = _file(1)
        assert _media_file(_msg(**{slot: attachment})) is attachment

    def test_returns_none_when_message_has_no_media(self) -> None:
        assert _media_file(_msg()) is None

    def test_voice_wins_over_other_slots(self) -> None:
        voice = _file(1)
        assert _media_file(_msg(voice=voice, document=_file(2))) is voice


class TestOversizedFileBytes:
    def test_file_over_the_limit_reports_its_size(self) -> None:
        over = _TELEGRAM_MAX_DOWNLOAD_BYTES + 1
        assert _oversized_file_bytes(_msg(voice=_file(over))) == over

    def test_file_exactly_at_the_limit_is_allowed(self) -> None:
        assert _oversized_file_bytes(_msg(voice=_file(_TELEGRAM_MAX_DOWNLOAD_BYTES))) is None

    def test_file_under_the_limit_is_allowed(self) -> None:
        assert _oversized_file_bytes(_msg(voice=_file(_TELEGRAM_MAX_DOWNLOAD_BYTES - 1))) is None

    def test_unknown_size_is_allowed_so_the_download_still_gets_a_chance(self) -> None:
        assert _oversized_file_bytes(_msg(voice=_file(None))) is None

    def test_message_without_media_is_allowed(self) -> None:
        assert _oversized_file_bytes(_msg()) is None

    @pytest.mark.parametrize(
        ("size_mb", "is_rejected"),
        [
            # Sizes from the four voice messages that exposed this: the first
            # two transcribed, the last two came back "file is too big".
            (15.5, False),
            (18.5, False),
            (22.9, True),
            (25.5, True),
        ],
    )
    def test_reproduces_the_observed_accept_reject_split(
        self, size_mb: float, is_rejected: bool
    ) -> None:
        msg = _msg(voice=_file(int(size_mb * _BYTES_PER_MB)))
        assert (_oversized_file_bytes(msg) is not None) is is_rejected
