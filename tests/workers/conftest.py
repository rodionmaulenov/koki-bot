"""Shared fixtures and helpers for workers tests."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import Settings
from models.manager import Manager
from models.user import User
from utils.time import TASHKENT_TZ

# ── Shared constants ─────────────────────────────────────────────────────────

JUN_15 = datetime(2025, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)
KOK_GROUP_ID = -1001234567890
GENERAL_TOPIC_ID = 42


# ── Shared factory functions ─────────────────────────────────────────────────


def make_user(
    user_id: int = 100, telegram_id: int | None = 555000,
    topic_id: int | None = 999, manager_id: int = 10,
) -> User:
    return User(
        id=user_id, telegram_id=telegram_id, name="Ivanova",
        manager_id=manager_id, topic_id=topic_id, created_at=JUN_15,
    )


def make_manager(manager_id: int = 10) -> Manager:
    return Manager(
        id=manager_id, telegram_id=777, name="Aliya",
        is_active=True, created_at=JUN_15,
    )


def make_settings(general_topic_id: int = GENERAL_TOPIC_ID) -> MagicMock:
    s = MagicMock(spec=Settings)
    s.kok_group_id = KOK_GROUP_ID
    s.kok_general_topic_id = general_topic_id
    return s


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client for dedup and worker tests."""
    return AsyncMock()
