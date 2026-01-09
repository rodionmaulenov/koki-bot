"""Тесты для CommandsMessagesService."""
import pytest


class TestCommandsMessagesService:
    """Тесты для сервиса хранения message_id."""

    @pytest.fixture
    def commands_messages_service(self, supabase):
        from app.services.commands_messages import CommandsMessagesService
        return CommandsMessagesService(supabase)

    @pytest.mark.asyncio
    async def test_add_message_id(self, commands_messages_service, supabase):
        """Добавление message_id."""
        # Очищаем таблицу
        await supabase.table("commands_messages").delete().neq("id", 0).execute()

        await commands_messages_service.add(12345)

        result = await supabase.table("commands_messages").select("*").execute()
        assert len(result.data) == 1
        assert result.data[0]["message_id"] == 12345

    @pytest.mark.asyncio
    async def test_get_all(self, commands_messages_service, supabase):
        """Получение всех message_id."""
        # Очищаем и добавляем тестовые данные
        await supabase.table("commands_messages").delete().neq("id", 0).execute()
        await supabase.table("commands_messages").insert([
            {"message_id": 100},
            {"message_id": 200},
            {"message_id": 300},
        ]).execute()

        result = await commands_messages_service.get_all()

        assert len(result) == 3
        assert 100 in result
        assert 200 in result
        assert 300 in result

    @pytest.mark.asyncio
    async def test_get_all_empty(self, commands_messages_service, supabase):
        """Получение пустого списка."""
        await supabase.table("commands_messages").delete().neq("id", 0).execute()

        result = await commands_messages_service.get_all()

        assert result == []

    @pytest.mark.asyncio
    async def test_delete_all(self, commands_messages_service, supabase):
        """Удаление всех записей."""
        # Добавляем тестовые данные
        await supabase.table("commands_messages").insert([
            {"message_id": 100},
            {"message_id": 200},
        ]).execute()

        await commands_messages_service.delete_all()

        result = await supabase.table("commands_messages").select("*").execute()
        assert len(result.data) == 0