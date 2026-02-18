from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class MenuAction(StrEnum):
    ADD = "add"
    REISSUE = "reissue"
    CLEAR = "clear"


class MenuCallback(CallbackData, prefix="menu"):
    action: MenuAction
