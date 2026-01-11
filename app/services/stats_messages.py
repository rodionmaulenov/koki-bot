"""Сервис для работы с сообщениями статистики."""

from datetime import datetime


class StatsMessagesService:
    """Управляет сообщениями дашбордов в БД."""

    def __init__(self, supabase, bot_type: str):
        self.supabase = supabase
        self.bot_type = bot_type

    async def get(self) -> dict | None:
        """Получить сообщение дашборда для этого бота."""
        result = await self.supabase.table("stats_messages") \
            .select("*") \
            .eq("bot_type", self.bot_type) \
            .maybe_single() \
            .execute()

        return result.data if result else None

    async def upsert(self, message_id: int) -> dict:
        """Создать или обновить запись."""
        result = await self.supabase.table("stats_messages") \
            .upsert({
                "bot_type": self.bot_type,
                "message_id": message_id,
                "updated_at": datetime.now().isoformat(),
            }, on_conflict="bot_type") \
            .execute()

        return result.data[0] if result.data else {}

    async def update_timestamp(self) -> None:
        """Обновить updated_at."""
        await self.supabase.table("stats_messages") \
            .update({"updated_at": datetime.now().isoformat()}) \
            .eq("bot_type", self.bot_type) \
            .execute()