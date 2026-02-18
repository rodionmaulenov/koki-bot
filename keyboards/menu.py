from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from callbacks.menu import MenuAction, MenuCallback


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="➕ Add",
                callback_data=MenuCallback(action=MenuAction.ADD).pack(),
            ),
            InlineKeyboardButton(
                text="🔗 Ссылка",
                callback_data=MenuCallback(action=MenuAction.REISSUE).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text="🗑 Clear",
                callback_data=MenuCallback(action=MenuAction.CLEAR).pack(),
            ),
        ],
    ])
