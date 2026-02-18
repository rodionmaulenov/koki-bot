from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks.reissue import ReissueCallback
from models.reissue import ReissueGirl


def reissue_list_keyboard(
    girls: Sequence[ReissueGirl],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for number, girl in enumerate(girls, start=1):
        builder.button(
            text=str(number),
            callback_data=ReissueCallback(course_id=girl.course_id),
        )
    builder.adjust(6)
    return builder.as_markup()
