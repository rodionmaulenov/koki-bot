"""Утилиты форматирования."""


def short_name(full_name: str) -> str:
    """Сокращает имя: Иванова Мария Петровна → Иванова М. П."""
    parts = full_name.split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}. {parts[2][0]}."
    return full_name