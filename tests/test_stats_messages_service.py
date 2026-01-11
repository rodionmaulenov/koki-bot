"""Тесты для StatsMessagesService."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.conftest import create_supabase_chain


class TestStatsMessagesService:
    """Тесты для StatsMessagesService."""

    @pytest.mark.asyncio
    async def test_get_found(self, mock_supabase):
        """Находит сообщение по bot_type."""
        from app.services.stats_messages import StatsMessagesService

        # maybe_single возвращает data как словарь, не список
        chain = MagicMock()
        chain.select = MagicMock(return_value=chain)
        chain.eq = MagicMock(return_value=chain)
        chain.maybe_single = MagicMock(return_value=chain)

        result = MagicMock()
        result.data = {"id": 1, "bot_type": "kok_dashboard", "message_id": 123}
        chain.execute = AsyncMock(return_value=result)

        mock_supabase.table = MagicMock(return_value=chain)

        service = StatsMessagesService(mock_supabase, "kok_dashboard")
        message = await service.get()

        assert message is not None
        assert message["message_id"] == 123
        chain.eq.assert_called_with("bot_type", "kok_dashboard")

    @pytest.mark.asyncio
    async def test_upsert(self, mock_supabase):
        """Upsert записи."""
        from app.services.stats_messages import StatsMessagesService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = StatsMessagesService(mock_supabase, "kok_dashboard")
        await service.upsert(message_id=456)

        chain.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_timestamp(self, mock_supabase):
        """Обновляет timestamp."""
        from app.services.stats_messages import StatsMessagesService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = StatsMessagesService(mock_supabase, "kok_dashboard")
        await service.update_timestamp()

        chain.update.assert_called_once()
        chain.eq.assert_called_with("bot_type", "kok_dashboard")