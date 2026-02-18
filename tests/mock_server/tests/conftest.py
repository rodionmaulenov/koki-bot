"""
Fixtures for mock server tests.
"""
import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage


@pytest.fixture
def simple_dispatcher() -> Dispatcher:
    """Create a simple dispatcher for testing."""
    return Dispatcher(storage=MemoryStorage())
