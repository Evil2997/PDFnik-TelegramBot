# repo: PDFnik-TelegramBot

"""
Closeable inline messages (feature 11).

Reusable keyboard helpers plus a single universal close handler:
any bot message sent with a "close" button can be dismissed by the user,
which simply deletes the message - no replacement, no confirmation.

Usage:
    await msg.answer(text, reply_markup=close_keyboard())          # info message
    markup = with_close_button(existing_markup)                    # extend keyboard
    register_close_handler(dp, bot)                                # once, at setup
"""

from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from main_app.core.logger import logger

CLOSE_CALLBACK_DATA = "action:close"
CLOSE_BUTTON_TEXT = "✖ Close"


def close_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text=CLOSE_BUTTON_TEXT, callback_data=CLOSE_CALLBACK_DATA)


def close_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with only the close button - for informational messages."""
    return InlineKeyboardMarkup(inline_keyboard=[[close_button()]])


def with_close_button(markup: InlineKeyboardMarkup | None = None) -> InlineKeyboardMarkup:
    """Returns a new keyboard: rows of `markup` (if any) plus a close row at the bottom.

    Does not mutate the original markup.
    """
    rows: list[list[InlineKeyboardButton]] = (
        [list(row) for row in markup.inline_keyboard] if markup else []
    )
    rows.append([close_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def register_close_handler(dp: Dispatcher, bot: Bot) -> None:
    @dp.callback_query(F.data == CLOSE_CALLBACK_DATA)
    async def on_close(callback: CallbackQuery) -> None:
        message = callback.message
        if message is None:
            await callback.answer()
            return

        # chat/message_id are present on both Message and InaccessibleMessage,
        # so deleting via the bot API works even for messages aiogram cannot
        # fully deserialize.
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception as exc:
            # Telegram forbids deleting messages older than 48h (and a few other
            # edge cases). Closing is best-effort - never surface an error.
            logger.info(
                "event=close_delete_failed chat_id=%s message_id=%s err=%s",
                message.chat.id,
                message.message_id,
                exc,
            )
            await callback.answer("Cannot close this message (too old?)")
            return

        await callback.answer()
