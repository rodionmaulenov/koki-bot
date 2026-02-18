from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class AppealAction(StrEnum):
    START = "start"      # Girl starts appeal
    ACCEPT = "accept"    # Manager accepts
    DECLINE = "decline"  # Manager declines


class AppealCallback(CallbackData, prefix="appeal"):
    action: AppealAction
    course_id: int
