from aiogram.filters.callback_data import CallbackData


class ReissueCallback(CallbackData, prefix="reissue"):
    course_id: int
