from aiogram.fsm.state import State, StatesGroup


class PaymentStates(StatesGroup):
    waiting_receipt = State()
