"""Tests for has_access() — 2 tests."""
from unittest.mock import AsyncMock

from topic_access.access import has_access


async def test_manager_has_access():
    """Manager → True."""
    mgr_repo = AsyncMock()
    mgr_repo.get_by_telegram_id.return_value = object()

    assert await has_access(123, mgr_repo) is True


async def test_non_manager_denied():
    """Not manager → False."""
    mgr_repo = AsyncMock()
    mgr_repo.get_by_telegram_id.return_value = None

    assert await has_access(123, mgr_repo) is False
