def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    """
    Русское склонение по числам:
    1 файл, 2 файла, 5 файлов
    1 сообщение, 2 сообщения, 5 сообщений
    """
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
        parts.append(f"{files} {_plural_ru(files, 'файл', 'файла', 'файлов')}")

    if photos > 0:
        # "фото" неизменяемое, но оставим единообразно
        parts.append(f"{photos} фото")

    if texts > 0:
        parts.append(
            f"{texts} {_plural_ru(texts, 'текстовое сообщение', 'текстовых сообщения', 'текстовых сообщений')}"
        )

    if not parts:
        return "Пока нечего собирать — отправьте текст или фото 🙂"

    return f"Собрал {', '.join(parts)}. Формирую PDF… 📄"
