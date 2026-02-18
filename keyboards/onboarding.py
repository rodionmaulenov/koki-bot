from datetime import time

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from callbacks.onboarding import OnboardingAction, OnboardingCallback
from templates import _t
from utils.time import get_tashkent_now


def instructions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=_t("Понятно", "Tushunarli"),
            callback_data=OnboardingCallback(
                action=OnboardingAction.UNDERSTOOD,
            ).pack(),
        )],
    ])


def cycle_day_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=_t(f"{day}-й день", f"{day}-kun"),
            callback_data=OnboardingCallback(
                action=OnboardingAction.CYCLE_DAY,
                value=str(day),
            ).pack(),
        )
        for day in range(1, 5)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[:2], buttons[2:]])


def intake_time_keyboard() -> InlineKeyboardMarkup:
    now = get_tashkent_now()
    current_minutes = now.hour * 60 + now.minute

    # Earliest slot: at least 30 min from now, rounded up to 30-min boundary
    earliest = current_minutes + 30
    next_slot = earliest + (-earliest % 30) if earliest % 30 else earliest

    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for minutes in range(next_slot, 24 * 60, 30):
        t = time(hour=minutes // 60, minute=minutes % 60)
        label = t.strftime("%H:%M")
        row.append(InlineKeyboardButton(
            text=label,
            callback_data=OnboardingCallback(
                action=OnboardingAction.TIME,
                value=label.replace(":", "-"),
            ).pack(),
        ))
        if len(row) == 4:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def rules_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=_t("Понятно", "Tushunarli"),
            callback_data=OnboardingCallback(
                action=OnboardingAction.RULES_OK,
            ).pack(),
        )],
    ])


def accept_terms_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=_t("Принимаю условия", "Shartlarni qabul qilaman"),
            callback_data=OnboardingCallback(
                action=OnboardingAction.ACCEPT,
            ).pack(),
        )],
    ])
