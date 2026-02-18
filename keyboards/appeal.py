from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from callbacks.appeal import AppealAction, AppealCallback
from templates import _t


def appeal_button(course_id: int) -> InlineKeyboardMarkup:
    """Single 'Appeal' button for girl's removal message."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=_t("Апелляция", "Apellyatsiya"),
                callback_data=AppealCallback(
                    action=AppealAction.START, course_id=course_id,
                ).pack(),
            ),
        ],
    ])


def appeal_review_keyboard(course_id: int) -> InlineKeyboardMarkup:
    """2 buttons for manager: Accept / Decline appeal."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Принять",
                callback_data=AppealCallback(
                    action=AppealAction.ACCEPT, course_id=course_id,
                ).pack(),
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=AppealCallback(
                    action=AppealAction.DECLINE, course_id=course_id,
                ).pack(),
            ),
        ],
    ])
