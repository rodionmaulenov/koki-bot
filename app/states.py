""""FSM состояния для диалогов."""

from aiogram.fsm.state import State, StatesGroup


class AddGirlStates(StatesGroup):
    """Состояния для /add."""
    waiting_for_name = State()


class AddVideoStates(StatesGroup):
    """Состояния для /add_video."""
    waiting_for_name = State()