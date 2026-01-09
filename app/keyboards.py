"""Клавиатуры для бота."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.utils.time_utils import get_tashkent_now

# Месяцы на русском (потом заменишь на узбекский)
MONTHS = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр",
    5: "май", 6: "июн", 7: "июл", 8: "авг",
    9: "сен", 10: "окт", 11: "ноя", 12: "дек",
}


def understand_button() -> InlineKeyboardMarkup:
    """Кнопка 'Понятно' после правил."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Понятно ✓", callback_data="understand")]
    ])


def cycle_day_keyboard() -> InlineKeyboardMarkup:
    """Кнопки выбора дня цикла (1-4) с текущей датой."""
    now = get_tashkent_now()
    day = now.day
    month = MONTHS[now.month]

    buttons = []
    for cycle_day in range(1, 5):
        buttons.append(
            InlineKeyboardButton(
                text=f"{cycle_day} день - {day} {month}",
                callback_data=f"cycle_{cycle_day}",
            )
        )

    keyboard = [
        [buttons[0], buttons[1]],
        [buttons[2], buttons[3]],
    ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def time_keyboard() -> InlineKeyboardMarkup:
    """Кнопки выбора времени (7:00 - 23:00) — для дней 1-3."""
    buttons = []
    for hour in range(7, 24):
        buttons.append(
            InlineKeyboardButton(
                text=f"{hour}:00",
                callback_data=f"time_{hour}_00",
            )
        )
        buttons.append(
            InlineKeyboardButton(
                text=f"{hour}:30",
                callback_data=f"time_{hour}_30",
            )
        )

    # По 4 кнопки в ряд
    keyboard = []
    for i in range(0, len(buttons), 4):
        keyboard.append(buttons[i:i + 4])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def time_keyboard_today() -> InlineKeyboardMarkup:
    """Кнопки выбора времени (сейчас + 30 мин до 23:00) — для дня 4."""
    now = get_tashkent_now()

    # Текущие минуты + 30
    current_minutes = now.hour * 60 + now.minute + 30

    # Округляем вверх до ближайших :00 или :30
    if current_minutes % 30 != 0:
        current_minutes = ((current_minutes // 30) + 1) * 30

    # Минимум 7:00
    start_minutes = max(current_minutes, 7 * 60)

    if start_minutes > 23 * 60 + 30:
        return None

    buttons = []
    for minutes in range(start_minutes, 24 * 60, 30):
        hour = minutes // 60
        minute = minutes % 60
        buttons.append(
            InlineKeyboardButton(
                text=f"{hour}:{minute:02d}",
                callback_data=f"time_{hour}_{minute:02d}",
            )
        )

    # По 4 кнопки в ряд
    keyboard = []
    for i in range(0, len(buttons), 4):
        keyboard.append(buttons[i:i + 4])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)