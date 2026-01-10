"""Тесты для CommandsMessagesService."""
import pytest
from unittest.mock import MagicMock

from tests.conftest import create_supabase_chain


class TestCommandsMessagesService:
    """Тесты для CommandsMessagesService."""

    @pytest.mark.asyncio
    async def test_add_new(self, mock_supabase):
        """Добавляет новый message_id."""
        from app.services.commands_messages import CommandsMessagesService

        # Первый вызов - проверка существования (пусто)
        # Второй вызов - insert
        select_chain = create_supabase_chain([])
        insert_chain = create_supabase_chain([{"id": 1, "message_id": 123}])

        mock_supabase.table = MagicMock(side_effect=[select_chain, insert_chain])

        service = CommandsMessagesService(mock_supabase)
        await service.add(123)

        insert_chain.insert.assert_called_once_with({"message_id": 123})

    @pytest.mark.asyncio
    async def test_get_all(self, mock_supabase):
        """Возвращает список message_id."""
        from app.services.commands_messages import CommandsMessagesService

        chain = create_supabase_chain([
            {"message_id": 100},
            {"message_id": 101},
        ])
        mock_supabase.table = MagicMock(return_value=chain)

        service = CommandsMessagesService(mock_supabase)
        messages = await service.get_all()

        assert messages == [100, 101]

    @pytest.mark.asyncio
    async def test_delete_all(self, mock_supabase):
        """Удаляет все записи."""
        from app.services.commands_messages import CommandsMessagesService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = CommandsMessagesService(mock_supabase)
        await service.delete_all()

        chain.delete.assert_called_once()