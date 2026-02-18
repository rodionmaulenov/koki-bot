from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class OnboardingAction(StrEnum):
    UNDERSTOOD = "understood"
    CYCLE_DAY = "day"
    TIME = "time"
    RULES_OK = "rules_ok"
    ACCEPT = "accept"


class OnboardingCallback(CallbackData, prefix="onb"):
    action: OnboardingAction
    value: str = ""
