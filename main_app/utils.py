def build_stats_message(files: int, photos: int, texts: int) -> str:
    parts = []

    if files == 1: parts.append("1 файл")
    elif files > 1: parts.append(f"{files} файлов")

    if photos == 1: parts.append("1 фото")
    elif photos > 1: parts.append(f"{photos} фото")

    if texts == 1: parts.append("1 текстовое сообщение")
    elif texts > 1: parts.append(f"{texts} текстовых сообщений")

    if not parts:
        return "Пока нечего собирать — отправьте текст или фото 🙂"

    return f"Собрал {', '.join(parts)}. Формирую PDF… 📄"
