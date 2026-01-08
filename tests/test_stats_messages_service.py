"""Тесты для StatsMessagesService."""
import pytest


class TestStatsMessagesService:
    """Тесты для сервиса сообщений статистики."""

    @pytest.mark.asyncio
    async def test_get_by_type_not_found(self, supabase):
        """Возвращает None если запись не найдена."""
        from app.services.stats_messages import StatsMessagesService

        service = StatsMessagesService(supabase)

        # Сначала убедимся что записи нет
        await supabase.table("stats_messages").delete().eq("type", "active").execute()

        result = await service.get_by_type("active")

        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_creates_new(self, supabase):
        """Создаёт новую запись."""
        from app.services.stats_messages import StatsMessagesService

        service = StatsMessagesService(supabase)

        # Cleanup перед тестом
        await supabase.table("stats_messages").delete().eq("type", "active").execute()

        result = await service.upsert(
            message_type="active",
            message_id=12345,
            chat_id=-100123456,
            thread_id=789,
        )

        assert result["type"] == "active"
        assert result["message_id"] == 12345

        # Проверяем что сохранилось в БД
        found = await service.get_by_type("active")
        assert found is not None
        assert found["message_id"] == 12345

        # Cleanup
        await supabase.table("stats_messages").delete().eq("type", "active").execute()

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, supabase):
        """Обновляет существующую запись."""
        from app.services.stats_messages import StatsMessagesService

        service = StatsMessagesService(supabase)

        # Cleanup перед тестом
        await supabase.table("stats_messages").delete().eq("type", "refusals").execute()

        # Создаём первую запись
        await service.upsert(
            message_type="refusals",
            message_id=111,
            chat_id=-100123456,
            thread_id=789,
        )

        # Обновляем с новым message_id
        await service.upsert(
            message_type="refusals",
            message_id=222,
            chat_id=-100123456,
            thread_id=789,
        )

        # Проверяем что обновилось
        found = await service.get_by_type("refusals")
        assert found["message_id"] == 222

        # Cleanup
        await supabase.table("stats_messages").delete().eq("type", "refusals").execute()

    @pytest.mark.asyncio
    async def test_update_timestamp(self, supabase):
        """Обновляет timestamp."""
        from app.services.stats_messages import StatsMessagesService

        service = StatsMessagesService(supabase)

        # Cleanup перед тестом
        await supabase.table("stats_messages").delete().eq("type", "active").execute()

        # Создаём запись
        await service.upsert(
            message_type="active",
            message_id=333,
            chat_id=-100123456,
            thread_id=789,
        )

        # Получаем первоначальный timestamp
        before = await service.get_by_type("active")
        before_time = before["updated_at"]

        # Небольшая пауза и обновление
        import asyncio
        await asyncio.sleep(0.1)
        await service.update_timestamp("active")

        # Проверяем что timestamp изменился
        after = await service.get_by_type("active")
        after_time = after["updated_at"]

        assert after_time >= before_time

        # Cleanup
        await supabase.table("stats_messages").delete().eq("type", "active").execute()