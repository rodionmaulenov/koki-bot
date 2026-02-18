from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class CardAction(StrEnum):
    EXTEND = "extend"
    COMPLETE = "complete"


class CardCallback(CallbackData, prefix="card"):
    action: CardAction
    course_id: int
