# /home/dmitriy/PycharmProjects/Telegram-Bot/tests/unit/test_bot_commands.py
# repo: PDFnik-TelegramBot

"""
Tests for commands.py and commands_text.py.

Tests only pure things without aiogram:
- command texts
- CANCEL text formatting
"""

from main_app.application.bot.commands_text import (
    CANCEL_CONFIRM_TEXT,
    CANCEL_CONFIRMED_TEXT,
    CANCEL_EMPTY_TEXT,
    HELP_TEXT,
    START_TEXT,
)


class TestStartText:
    def test_not_empty(self):
        assert len(START_TEXT.strip()) > 50

    def test_mentions_done_command(self):
        assert "/done" in START_TEXT

    def test_mentions_pdf(self):
        assert "PDF" in START_TEXT

    def test_mentions_youtube(self):
        assert "YouTube" in START_TEXT or "youtube" in START_TEXT.lower()

    def test_mentions_voice(self):
        assert "voice" in START_TEXT.lower() or "голос" in START_TEXT.lower()


class TestHelpText:
    def test_not_empty(self):
        assert len(HELP_TEXT.strip()) > 50

    def test_contains_done(self):
        assert "/done" in HELP_TEXT

    def test_contains_cancel(self):
        assert "/cancel" in HELP_TEXT

    def test_contains_help(self):
        assert "/help" in HELP_TEXT

    def test_mentions_youtube(self):
        assert "YouTube" in HELP_TEXT or "youtube" in HELP_TEXT.lower()

    def test_mentions_photo(self):
        assert "photo" in HELP_TEXT.lower() or "фото" in HELP_TEXT.lower()


class TestCancelTexts:
    def test_empty_text_defined(self):
        assert len(CANCEL_EMPTY_TEXT.strip()) > 5

    def test_confirm_text_has_placeholders(self):
        formatted = CANCEL_CONFIRM_TEXT.format(photo_count=3, text_count=2)
        assert "3" in formatted
        assert "2" in formatted

    def test_confirmed_text_has_placeholders(self):
        formatted = CANCEL_CONFIRMED_TEXT.format(photo_count=1, text_count=5)
        assert "1" in formatted
        assert "5" in formatted

    def test_confirm_text_mentions_cancel(self):
        assert "/cancel" in CANCEL_CONFIRM_TEXT

    def test_confirmed_text_not_empty(self):
        assert len(CANCEL_CONFIRMED_TEXT.strip()) > 5
