from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class VideoAction(StrEnum):
    CONFIRM = "confirm"
    RESHOOT = "reshoot"
    REJECT = "reject"


class VideoCallback(CallbackData, prefix="vid"):
    action: VideoAction
    log_id: int
