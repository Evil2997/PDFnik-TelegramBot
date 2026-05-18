# /home/dmitriy/PycharmProjects/Telegram-Bot/tests/unit/test_build_stats_message.py
# repo: PDFnik-TelegramBot


from main_app.domain.build_stats_message import build_stats_message


class TestBuildStatsMessage:
    def test_all_zero_returns_fallback(self):
        msg = build_stats_message(0, 0, 0)
        assert len(msg) > 0

    def test_only_one_photo(self):
        msg = build_stats_message(0, 1, 0)
        assert "1 photo" in msg
        assert "photos" not in msg  # singular form

    def test_only_photos_plural(self):
        msg = build_stats_message(0, 3, 0)
        assert "3 photos" in msg

    def test_only_one_text(self):
        msg = build_stats_message(0, 0, 1)
        assert "1 text message" in msg
        assert "messages" not in msg  # singular form

    def test_texts_plural_two(self):
        msg = build_stats_message(0, 0, 2)
        assert "2 text messages" in msg

    def test_texts_plural_five(self):
        msg = build_stats_message(0, 0, 5)
        assert "5 text messages" in msg

    def test_mixed_photos_and_texts(self):
        msg = build_stats_message(0, 2, 3)
        assert "2 photos" in msg
        assert "3 text messages" in msg

    def test_message_contains_pdf(self):
        msg = build_stats_message(0, 1, 1)
        assert "PDF" in msg
