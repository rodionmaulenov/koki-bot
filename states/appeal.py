from aiogram.fsm.state import State, StatesGroup


class AppealStates(StatesGroup):
    video = State()
    text = State()
