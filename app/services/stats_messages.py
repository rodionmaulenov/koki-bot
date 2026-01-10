"""Сервис для работы с сообщениями статистики."""

from datetime import datetime


class StatsMessagesService:
    """Управляет сообщениями дашбордов в БД."""

    def __init__(self, supabase):
        self.supabase = supabase

    async def get_by_type(self, message_type: str) -> dict | None:
        """Получить сообщение по типу (active/refusals)."""
        result = await self.supabase.table("stats_messages") \
            .select("*") \
            .eq("type", message_type) \
            .maybe_single() \
            .execute()

        return result.data if result else None

    async def upsert(
        self,
        message_type: str,
        message_id: int,
    ) -> dict:
        """Создать или обновить запись."""
        result = await self.supabase.table("stats_messages") \
            .upsert({
                "type": message_type,
                "message_id": message_id,
                "updated_at": datetime.now().isoformat(),
            }, on_conflict="type") \
            .execute()

        return result.data[0] if result.data else {}

    async def update_timestamp(self, message_type: str) -> None:
        """Обновить updated_at."""
        await self.supabase.table("stats_messages") \
            .update({"updated_at": datetime.now().isoformat()}) \
            .eq("type", message_type) \
            .execute()