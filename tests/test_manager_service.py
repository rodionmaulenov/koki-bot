"""Тесты для ManagerService."""
import pytest


class TestManagerServiceGetByTelegramId:
    """Тесты для get_by_telegram_id()."""

    @pytest.mark.asyncio
    async def test_finds_manager(self, manager_service, test_manager):
        """Находит менеджера по telegram_id."""
        manager = await manager_service.get_by_telegram_id(test_manager["telegram_id"])

        assert manager is not None
        assert manager["id"] == test_manager["id"]
        assert manager["name"] == test_manager["name"]

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, manager_service):
        """Возвращает None для несуществующего telegram_id."""
        manager = await manager_service.get_by_telegram_id(999999999)

        assert manager is None


class TestManagerServiceGetById:
    """Тесты для get_by_id()."""

    @pytest.mark.asyncio
    async def test_finds_manager(self, manager_service, test_manager):
        """Находит менеджера по id."""
        manager = await manager_service.get_by_id(test_manager["id"])

        assert manager is not None
        assert manager["telegram_id"] == test_manager["telegram_id"]

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, manager_service):
        """Возвращает None для несуществующего id."""
        manager = await manager_service.get_by_id(999999999)

        assert manager is None