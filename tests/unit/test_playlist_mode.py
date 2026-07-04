# repo: PDFnik-TelegramBot

"""
Tests for playlist_mode.py helpers (previously uncovered).

Covers:
- pending-playlist Redis key helpers (store / pop / miss)
- make_mode_keyboard layout, including the appended close row (feature 11)
"""

from unittest.mock import AsyncMock, MagicMock

from main_app.application.bot.closeable import CLOSE_CALLBACK_DATA
from main_app.application.bot.playlist_mode import (
    _MODES,
    _PENDING_TTL_SEC,
    _pending_key,
    make_mode_keyboard,
    pop_pending_playlist,
    store_pending_playlist,
)

# ---------------------------------------------------------------------------
# Pending playlist storage
# ---------------------------------------------------------------------------


class TestPendingKey:
    def test_format(self):
        assert _pending_key(12, 34) == "playlist_mode_pending:12:34"

    def test_distinct_per_message(self):
        assert _pending_key(1, 2) != _pending_key(1, 3)


class TestStorePendingPlaylist:
    async def test_sets_with_ttl(self):
        redis = MagicMock()
        redis.set = AsyncMock()

        await store_pending_playlist(redis, 12, 34, "https://youtu.be/x")

        redis.set.assert_awaited_once_with(
            "playlist_mode_pending:12:34", "https://youtu.be/x", ex=_PENDING_TTL_SEC
        )


class TestPopPendingPlaylist:
    async def test_returns_and_deletes_on_hit(self):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=b"https://youtu.be/x")
        redis.delete = AsyncMock()

        url = await pop_pending_playlist(redis, 12, 34)

        assert url == "https://youtu.be/x"
        redis.delete.assert_awaited_once_with("playlist_mode_pending:12:34")

    async def test_decodes_str_value(self):
        redis = MagicMock()
        redis.get = AsyncMock(return_value="https://youtu.be/y")
        redis.delete = AsyncMock()

        assert await pop_pending_playlist(redis, 1, 2) == "https://youtu.be/y"

    async def test_returns_none_on_miss(self):
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.delete = AsyncMock()

        assert await pop_pending_playlist(redis, 1, 2) is None
        redis.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# Mode keyboard
# ---------------------------------------------------------------------------


class TestMakeModeKeyboard:
    def test_mode_buttons_two_per_row(self):
        kb = make_mode_keyboard(original_message_id=7)
        mode_rows = kb.inline_keyboard[:-1]  # last row is the close row
        buttons = [btn for row in mode_rows for btn in row]
        assert len(buttons) == len(_MODES)
        assert all(len(row) <= 2 for row in mode_rows)

    def test_mode_labels(self):
        kb = make_mode_keyboard(original_message_id=7)
        labels = [btn.text for row in kb.inline_keyboard[:-1] for btn in row]
        assert labels == [label for _, label in _MODES]

    def test_callback_data_carries_mode_and_message_id(self):
        kb = make_mode_keyboard(original_message_id=7)
        first = kb.inline_keyboard[0][0]
        assert first.callback_data is not None
        assert first.callback_data.startswith("plm:")
        assert ":7" in first.callback_data

    def test_last_row_is_close_button(self):
        kb = make_mode_keyboard(original_message_id=7)
        close_row = kb.inline_keyboard[-1]
        assert len(close_row) == 1
        assert close_row[0].callback_data == CLOSE_CALLBACK_DATA
