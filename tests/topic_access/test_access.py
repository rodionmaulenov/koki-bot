"""Tests for has_access() — 5 tests."""
from unittest.mock import AsyncMock

from topic_access.access import has_access


async def test_manager_has_access():
    """Manager → True."""
    mgr_repo = AsyncMock()
    own_repo = AsyncMock()
    mgr_repo.get_by_telegram_id.return_value = object()

    assert await has_access(123, mgr_repo, own_repo) is True


async def test_owner_has_access():
    """Owner (not manager) → True."""
    mgr_repo = AsyncMock()
    own_repo = AsyncMock()
    mgr_repo.get_by_telegram_id.return_value = None
    own_repo.get_by_telegram_id.return_value = object()

    assert await has_access(123, mgr_repo, own_repo) is True


async def test_neither_returns_false():
    """Not manager, not owner → False."""
    mgr_repo = AsyncMock()
    own_repo = AsyncMock()
    mgr_repo.get_by_telegram_id.return_value = None
    own_repo.get_by_telegram_id.return_value = None

    assert await has_access(123, mgr_repo, own_repo) is False


async def test_manager_short_circuits_owner_check():
    """When manager found, owner_repo is NOT called."""
    mgr_repo = AsyncMock()
    own_repo = AsyncMock()
    mgr_repo.get_by_telegram_id.return_value = object()

    await has_access(123, mgr_repo, own_repo)

    own_repo.get_by_telegram_id.assert_not_called()


async def test_no_manager_checks_owner():
    """When no manager, owner_repo IS called with correct telegram_id."""
    mgr_repo = AsyncMock()
    own_repo = AsyncMock()
    mgr_repo.get_by_telegram_id.return_value = None
    own_repo.get_by_telegram_id.return_value = None

    await has_access(777, mgr_repo, own_repo)

    own_repo.get_by_telegram_id.assert_called_once_with(777)