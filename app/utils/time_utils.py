from datetime import datetime, time
from zoneinfo import ZoneInfo

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")  # UTC+5

MONTHS = {
    1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр",
    5: "Май", 6: "Июн", 7: "Июл", 8: "Авг",
    9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
}


def format_date(date_str: str) -> str:
    """Форматирует дату: 2026-01-06 → 6 Янв 26"""
    from datetime import datetime

    try:
        date = datetime.fromisoformat(date_str).date()
        month = MONTHS[date.month]
        year = str(date.year)[2:]  # 2026 → 26
        return f"{date.day} {month} {year}"
    except (ValueError, TypeError):
        return date_str


def get_tashkent_now() -> datetime:
    """Текущее время в Ташкенте."""
    return datetime.now(TASHKENT_TZ)


def parse_time_string(time_str: str) -> time | None:
    """
    Парсит время из строки.
    Примеры: "15", "15:00", "15:30", "morning", "вечером"
    """
    if not time_str:
        return None

    s = time_str.lower().strip()

    # Словесные варианты
    words = {
        "morning": (9, 0), "утром": (9, 0), "утро": (9, 0),
        "днём": (14, 0), "днем": (14, 0), "день": (14, 0),
        "вечером": (19, 0), "вечер": (19, 0), "evening": (19, 0),
    }
    if s in words:
        h, m = words[s]
        return time(h, m)

    # Числовой формат: "15" или "15:00" или "15:30"
    try:
        if ":" in s:
            parts = s.split(":")
            return time(int(parts[0]), int(parts[1]))
        else:
            # Убираем лишнее: "в 15", "15 часов"
            digits = "".join(c for c in s if c.isdigit())
            if digits:
                hour = int(digits)
                if 0 <= hour <= 23:
                    return time(hour, 0)
    except (ValueError, IndexError):
        pass

    return None


def is_time_passed(user_time: time) -> bool:
    """Прошло ли указанное время сегодня по Ташкенту."""
    now = get_tashkent_now()
    return now.hour > user_time.hour or (
            now.hour == user_time.hour and now.minute > user_time.minute
    )


def calculate_delay_minutes(intake_time: str, current_time: str) -> int:
    """Вычисляет опоздание в минутах.

    Args:
        intake_time: Время приёма таблетки, например "12:00" или "12:00:00"
        current_time: Текущее время, например "14:30" или "14:30:00"

    Returns:
        Опоздание в минутах. Если вовремя или раньше — возвращает 0.
    """
    try:
        # Парсим intake_time (может быть "12:00" или "12:00:00")
        intake_parts = intake_time.split(":")
        intake_h = int(intake_parts[0])
        intake_m = int(intake_parts[1]) if len(intake_parts) > 1 else 0

        # Парсим current_time
        current_parts = current_time.split(":")
        current_h = int(current_parts[0])
        current_m = int(current_parts[1]) if len(current_parts) > 1 else 0

        intake_minutes = intake_h * 60 + intake_m
        current_minutes = current_h * 60 + current_m

        delay = current_minutes - intake_minutes
        return max(0, delay)
    except (ValueError, AttributeError, TypeError):
        return 0


def calculate_time_range_before(minutes_before: int, tolerance: int = 5) -> tuple[str, str]:
    """Вычисляет диапазон времени в будущем (для reminders).

    Пример: сейчас 11:00, minutes_before=60 → ищем intake_time 12:00
    """
    now = get_tashkent_now()
    current_minutes = now.hour * 60 + now.minute

    target_minutes = current_minutes + minutes_before
    target_hour = (target_minutes // 60) % 24
    target_minute = target_minutes % 60

    min_minute = max(0, target_minute - tolerance)
    max_minute = min(59, target_minute + tolerance)

    return f"{target_hour:02d}:{min_minute:02d}", f"{target_hour:02d}:{max_minute:02d}"


def calculate_time_range_after(minutes_after: int, tolerance: int = 5) -> tuple[str, str]:
    """Вычисляет диапазон времени в прошлом (для alerts/refusals).

    Пример: сейчас 12:30, minutes_after=30 → ищем intake_time 12:00
    """
    now = get_tashkent_now()
    current_minutes = now.hour * 60 + now.minute

    target_minutes = current_minutes - minutes_after
    if target_minutes < 0:
        target_minutes += 24 * 60

    target_hour = (target_minutes // 60) % 24
    target_minute = target_minutes % 60

    min_minute = max(0, target_minute - tolerance)
    max_minute = min(59, target_minute + tolerance)

    return f"{target_hour:02d}:{min_minute:02d}", f"{target_hour:02d}:{max_minute:02d}"


def is_too_early(intake_time: str, minutes_before: int = 10) -> tuple[bool, str]:
    """Проверяет не слишком ли рано для видео.

    Returns:
        (True, "11:50") — слишком рано, окно откроется в 11:50
        (False, "") — можно отправлять
    """
    now = get_tashkent_now()
    current_minutes = now.hour * 60 + now.minute

    parts = intake_time.split(":")
    intake_h = int(parts[0])
    intake_m = int(parts[1]) if len(parts) > 1 else 0
    intake_minutes = intake_h * 60 + intake_m

    window_start = intake_minutes - minutes_before

    if current_minutes < window_start:
        start_h = window_start // 60
        start_m = window_start % 60
        return True, f"{start_h:02d}:{start_m:02d}"

    return False, ""
