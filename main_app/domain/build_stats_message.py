# /home/dmitriy/PycharmProjects/Telegram-Bot/main_app/domain/build_stats_message.py
# repo: PDFnik-TelegramBot


def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    n_abs = abs(n) % 100
    if 11 <= n_abs <= 14:
        return many
    last = n_abs % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def build_stats_message(files: int, photos: int, texts: int) -> str:
    parts: list[str] = []

    if files > 0:
        parts.append(f"{files} {'file' if files == 1 else 'files'}")

    if photos > 0:
        parts.append(f"{photos} {'photo' if photos == 1 else 'photos'}")

    if texts > 0:
        parts.append(f"{texts} text {'message' if texts == 1 else 'messages'}")

    if not parts:
        return "Nothing to collect yet — send some text or photos 🙂"

    return f"Collected {', '.join(parts)}. Building PDF... 📄"
