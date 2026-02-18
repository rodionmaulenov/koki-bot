from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from callbacks.card import CardAction, CardCallback


def card_keyboard(course_id: int, can_extend: bool) -> InlineKeyboardMarkup:
    """Buttons on registration card in topic: Extend / Complete."""
    rows: list[list[InlineKeyboardButton]] = []
    if can_extend:
        rows.append([
            InlineKeyboardButton(
                text="Продлить +21 день",
                callback_data=CardCallback(
                    action=CardAction.EXTEND, course_id=course_id,
                ).pack(),
            ),
        ])
    rows.append([
        InlineKeyboardButton(
            text="Завершить программу",
            callback_data=CardCallback(
                action=CardAction.COMPLETE, course_id=course_id,
            ).pack(),
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
