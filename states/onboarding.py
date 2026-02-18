from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    instructions = State()
    cycle_day = State()
    intake_time = State()
    rules = State()
    accept_terms = State()
