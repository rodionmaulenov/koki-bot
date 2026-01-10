"""Тесты для StatsMessagesService."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.conftest import create_supabase_chain


class TestStatsMessagesService:
    """Тесты для StatsMessagesService."""

    @pytest.mark.asyncio
    async def test_get_by_type_found(self, mock_supabase):
        """Находит сообщение по типу."""
        from app.services.stats_messages import StatsMessagesService

        # maybe_single возвращает data как словарь, не список
        chain = MagicMock()
        chain.select = MagicMock(return_value=chain)
        chain.eq = MagicMock(return_value=chain)
        chain.maybe_single = MagicMock(return_value=chain)

        result = MagicMock()
        result.data = {"id": 1, "type": "kok_dashboard", "message_id": 123}
        chain.execute = AsyncMock(return_value=result)

        mock_supabase.table = MagicMock(return_value=chain)

        service = StatsMessagesService(mock_supabase)
        message = await service.get_by_type("kok_dashboard")

        assert message is not None
        assert message["message_id"] == 123

    @pytest.mark.asyncio
    async def test_upsert(self, mock_supabase):
        """Upsert записи."""
        from app.services.stats_messages import StatsMessagesService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = StatsMessagesService(mock_supabase)
        await service.upsert(message_type="kok_dashboard", message_id=456)

        chain.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_timestamp(self, mock_supabase):
        """Обновляет timestamp."""
        from app.services.stats_messages import StatsMessagesService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = StatsMessagesService(mock_supabase)
        await service.update_timestamp("kok_dashboard")

        chain.update.assert_called_once()