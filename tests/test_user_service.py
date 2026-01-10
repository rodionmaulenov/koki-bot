"""Тесты для UserService."""
import pytest
from unittest.mock import MagicMock

from tests.conftest import create_supabase_chain


class TestUserService:
    """Тесты для UserService."""

    @pytest.mark.asyncio
    async def test_create(self, mock_supabase):
        """Создаёт пользователя."""
        from app.services.users import UserService

        chain = create_supabase_chain([{"id": 1, "name": "Тестова Мария", "manager_id": 1}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = UserService(mock_supabase)
        user = await service.create(name="Тестова Мария", manager_id=1)

        assert user["name"] == "Тестова Мария"

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, mock_supabase):
        """Находит пользователя по ID."""
        from app.services.users import UserService

        chain = create_supabase_chain([{"id": 1, "name": "Тестова Мария"}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = UserService(mock_supabase)
        user = await service.get_by_id(1)

        assert user is not None
        assert user["name"] == "Тестова Мария"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mock_supabase):
        """Возвращает None если не найден."""
        from app.services.users import UserService

        chain = create_supabase_chain([])
        mock_supabase.table = MagicMock(return_value=chain)

        service = UserService(mock_supabase)
        user = await service.get_by_id(999)

        assert user is None

    @pytest.mark.asyncio
    async def test_get_by_telegram_id_found(self, mock_supabase):
        """Находит пользователя по telegram_id."""
        from app.services.users import UserService

        chain = create_supabase_chain([{"id": 1, "telegram_id": 123456789}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = UserService(mock_supabase)
        user = await service.get_by_telegram_id(123456789)

        assert user is not None
        assert user["telegram_id"] == 123456789

    @pytest.mark.asyncio
    async def test_set_telegram_id(self, mock_supabase):
        """Устанавливает telegram_id."""
        from app.services.users import UserService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = UserService(mock_supabase)
        await service.set_telegram_id(user_id=1, telegram_id=123456789)

        calls = chain.update.call_args_list
        assert any(call[0][0].get("telegram_id") == 123456789 for call in calls)

    @pytest.mark.asyncio
    async def test_set_topic_id(self, mock_supabase):
        """Устанавливает topic_id."""
        from app.services.users import UserService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = UserService(mock_supabase)
        await service.set_topic_id(user_id=1, topic_id=456)

        chain.update.assert_called_once_with({"topic_id": 456})

    @pytest.mark.asyncio
    async def test_get_by_name_and_manager_found(self, mock_supabase):
        """Находит пользователя по имени и менеджеру."""
        from app.services.users import UserService

        chain = create_supabase_chain([{"id": 1, "name": "Тестова Мария", "manager_id": 1}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = UserService(mock_supabase)
        user = await service.get_by_name_and_manager("Тестова", 1)

        assert user is not None
        assert user["name"] == "Тестова Мария"