"""Тесты для states.py."""
from aiogram.fsm.state import StatesGroup

from app.states import AddGirlStates, AddVideoStates


class TestAddGirlStates:
    """Тесты для AddGirlStates."""

    def test_is_states_group(self):
        """Является StatesGroup."""
        assert issubclass(AddGirlStates, StatesGroup)

    def test_has_waiting_for_name(self):
        """Имеет состояние waiting_for_name."""
        assert hasattr(AddGirlStates, "waiting_for_name")

    def test_state_name(self):
        """Правильное имя состояния."""
        state = AddGirlStates.waiting_for_name
        assert "waiting_for_name" in str(state)


class TestAddVideoStates:
    """Тесты для AddVideoStates."""

    def test_is_states_group(self):
        """Является StatesGroup."""
        assert issubclass(AddVideoStates, StatesGroup)

    def test_has_waiting_for_name(self):
        """Имеет состояние waiting_for_name."""
        assert hasattr(AddVideoStates, "waiting_for_name")

    def test_state_name(self):
        """Правильное имя состояния."""
        state = AddVideoStates.waiting_for_name
        assert "waiting_for_name" in str(state)