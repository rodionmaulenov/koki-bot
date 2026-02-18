from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from callbacks.payment import PaymentCallback


def payment_receipt_keyboard(course_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="\U0001f4ce Отправить чек",
                callback_data=PaymentCallback(
                    action="send", course_id=course_id,
                ).pack(),
            ),
        ],
    ])


def payment_cancel_keyboard(course_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="\u274c Отменить",
                callback_data=PaymentCallback(
                    action="cancel", course_id=course_id,
                ).pack(),
            ),
        ],
    ])
