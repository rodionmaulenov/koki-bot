from aiogram.fsm.state import State, StatesGroup


class AddStates(StatesGroup):
    waiting_passport = State()
    waiting_receipt = State()
    waiting_card = State()
