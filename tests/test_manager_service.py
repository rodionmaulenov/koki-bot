"""Тесты для ManagerService."""
import pytest
from unittest.mock import MagicMock

from tests.conftest import create_supabase_chain


class TestManagerService:
    """Тесты для ManagerService."""

    @pytest.mark.asyncio
    async def test_get_by_telegram_id_found(self, mock_supabase):
        """Находит менеджера по telegram_id."""
        from app.services.managers import ManagerService

        chain = create_supabase_chain([{"id": 1, "telegram_id": 123456789, "name": "Test"}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = ManagerService(mock_supabase)
        manager = await service.get_by_telegram_id(123456789)

        assert manager is not None
        assert manager["name"] == "Test"

    @pytest.mark.asyncio
    async def test_get_by_telegram_id_not_found(self, mock_supabase):
        """Возвращает None если не найден."""
        from app.services.managers import ManagerService

        chain = create_supabase_chain([])
        mock_supabase.table = MagicMock(return_value=chain)

        service = ManagerService(mock_supabase)
        manager = await service.get_by_telegram_id(999999)

        assert manager is None

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, mock_supabase):
        """Находит менеджера по ID."""
        from app.services.managers import ManagerService

        chain = create_supabase_chain([{"id": 1, "name": "Test Manager"}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = ManagerService(mock_supabase)
        manager = await service.get_by_id(1)

        assert manager is not None
        assert manager["name"] == "Test Manager"