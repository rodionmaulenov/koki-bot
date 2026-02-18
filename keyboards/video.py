from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from callbacks.video import VideoAction, VideoCallback


def review_keyboard(log_id: int) -> InlineKeyboardMarkup:
    """3 buttons: Confirm / Reshoot / Reject (one per row for mobile)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Принять",
            callback_data=VideoCallback(
                action=VideoAction.CONFIRM, log_id=log_id,
            ).pack(),
        )],
        [InlineKeyboardButton(
            text="🔄 Переснять",
            callback_data=VideoCallback(
                action=VideoAction.RESHOOT, log_id=log_id,
            ).pack(),
        )],
        [InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=VideoCallback(
                action=VideoAction.REJECT, log_id=log_id,
            ).pack(),
        )],
    ])


def reshoot_review_keyboard(log_id: int) -> InlineKeyboardMarkup:
    """2 buttons: Confirm / Reject (reshoot video, no second reshoot)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Принять",
                callback_data=VideoCallback(
                    action=VideoAction.CONFIRM, log_id=log_id,
                ).pack(),
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=VideoCallback(
                    action=VideoAction.REJECT, log_id=log_id,
                ).pack(),
            ),
        ],
    ])
