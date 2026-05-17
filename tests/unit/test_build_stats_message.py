# /home/dmitriy/PycharmProjects/Telegram-Bot/tests/unit/test_build_stats_message.py
# repo: PDFnik-TelegramBot


from main_app.domain.build_stats_message import _plural_ru, build_stats_message

# ---------------------------------------------------------------------------
# _plural_ru
# ---------------------------------------------------------------------------


class TestPluralRu:
    def test_one(self):
        assert _plural_ru(1, "файл", "файла", "файлов") == "файл"

    def test_two(self):
        assert _plural_ru(2, "файл", "файла", "файлов") == "файла"

    def test_five(self):
        assert _plural_ru(5, "файл", "файла", "файлов") == "файлов"

    def test_eleven(self):
        assert _plural_ru(11, "файл", "файла", "файлов") == "файлов"

    def test_twelve(self):
        assert _plural_ru(12, "файл", "файла", "файлов") == "файлов"

    def test_twenty_one(self):
        assert _plural_ru(21, "файл", "файла", "файлов") == "файл"

    def test_hundred_one(self):
        assert _plural_ru(101, "файл", "файла", "файлов") == "файл"

    def test_zero(self):
        assert _plural_ru(0, "файл", "файла", "файлов") == "файлов"


# ---------------------------------------------------------------------------
# build_stats_message
# ---------------------------------------------------------------------------


class TestBuildStatsMessage:
    def test_all_zero_returns_fallback(self):
        msg = build_stats_message(0, 0, 0)
        assert len(msg) > 0

    def test_only_photos(self):
        msg = build_stats_message(0, 3, 0)
        assert "3 фото" in msg

    def test_only_one_text(self):
        msg = build_stats_message(0, 0, 1)
        assert "1 текстовое сообщение" in msg

    def test_texts_plural_five(self):
        msg = build_stats_message(0, 0, 5)
        assert "5 текстовых сообщений" in msg

    def test_texts_plural_two(self):
        msg = build_stats_message(0, 0, 2)
        assert "2 текстовых сообщения" in msg

    def test_mixed_photos_and_texts(self):
        msg = build_stats_message(0, 2, 3)
        assert "2 фото" in msg
        assert "3 текстовых сообщения" in msg

    def test_message_contains_pdf(self):
        msg = build_stats_message(0, 1, 1)
        assert "PDF" in msg
