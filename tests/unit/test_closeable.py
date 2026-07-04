# repo: PDFnik-TelegramBot

"""
Tests for closeable.py (feature 11: closeable inline messages).

Covers:
- keyboard builders (close_button / close_keyboard / with_close_button)
- the universal close callback handler (delete, ack, failure fallback)
"""

from unittest.mock import AsyncMock, MagicMock

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from main_app.application.bot.closeable import (
    CLOSE_BUTTON_TEXT,
    CLOSE_CALLBACK_DATA,
    close_button,
    close_keyboard,
    register_close_handler,
    with_close_button,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_close_handler(bot: MagicMock):
    """Registers the close handler on a fake dispatcher and returns it."""
    dp = MagicMock()
    handlers: list = []

    def fake_callback_query(*filters):
        def decorator(fn):
            handlers.append(fn)
            return fn

        return decorator

    dp.callback_query = fake_callback_query
    register_close_handler(dp, bot)
    assert len(handlers) == 1
    return handlers[0]


def _make_callback(chat_id: int = 100, message_id: int = 42) -> MagicMock:
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.chat.id = chat_id
    callback.message.message_id = message_id
    callback.answer = AsyncMock()
    return callback


# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------


class TestCloseButton:
    def test_callback_data(self):
        assert close_button().callback_data == CLOSE_CALLBACK_DATA

    def test_callback_data_value(self):
        assert CLOSE_CALLBACK_DATA == "action:close"

    def test_text(self):
        assert close_button().text == CLOSE_BUTTON_TEXT
        assert "✖" in CLOSE_BUTTON_TEXT


class TestCloseKeyboard:
    def test_single_row_single_button(self):
        kb = close_keyboard()
        assert len(kb.inline_keyboard) == 1
        assert len(kb.inline_keyboard[0]) == 1
        assert kb.inline_keyboard[0][0].callback_data == CLOSE_CALLBACK_DATA


class TestWithCloseButton:
    def test_none_markup_gives_close_only_keyboard(self):
        kb = with_close_button(None)
        assert len(kb.inline_keyboard) == 1
        assert kb.inline_keyboard[0][0].callback_data == CLOSE_CALLBACK_DATA

    def test_default_arg_is_none(self):
        assert with_close_button().inline_keyboard == close_keyboard().inline_keyboard

    def test_appends_close_row_after_existing_rows(self):
        original = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="A", callback_data="a")],
                [InlineKeyboardButton(text="B", callback_data="b")],
            ]
        )
        kb = with_close_button(original)
        assert len(kb.inline_keyboard) == 3
        assert kb.inline_keyboard[0][0].text == "A"
        assert kb.inline_keyboard[1][0].text == "B"
        assert kb.inline_keyboard[2][0].callback_data == CLOSE_CALLBACK_DATA

    def test_does_not_mutate_original(self):
        original = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="A", callback_data="a")]]
        )
        with_close_button(original)
        assert len(original.inline_keyboard) == 1


# ---------------------------------------------------------------------------
# Universal close handler
# ---------------------------------------------------------------------------


class TestCloseHandler:
    async def test_deletes_message_and_acks(self):
        bot = MagicMock()
        bot.delete_message = AsyncMock()
        handler = _capture_close_handler(bot)

        callback = _make_callback(chat_id=100, message_id=42)
        await handler(callback)

        bot.delete_message.assert_awaited_once_with(chat_id=100, message_id=42)
        callback.answer.assert_awaited_once_with()

    async def test_no_message_just_acks(self):
        bot = MagicMock()
        bot.delete_message = AsyncMock()
        handler = _capture_close_handler(bot)

        callback = _make_callback()
        callback.message = None
        await handler(callback)

        bot.delete_message.assert_not_awaited()
        callback.answer.assert_awaited_once()

    async def test_delete_failure_still_acks_without_raising(self):
        bot = MagicMock()
        bot.delete_message = AsyncMock(side_effect=RuntimeError("message too old"))
        handler = _capture_close_handler(bot)

        callback = _make_callback()
        await handler(callback)

        callback.answer.assert_awaited_once()
        # The failure ack carries an explanatory text
        assert callback.answer.call_args[0]
