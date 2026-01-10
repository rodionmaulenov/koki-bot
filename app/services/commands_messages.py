"""Сервис для хранения ID сообщений в топике Команды."""

import logging
from supabase.client import AsyncClient

logger = logging.getLogger(__name__)


class CommandsMessagesService:
    def __init__(self, supabase: AsyncClient):
        self.supabase = supabase

    async def add(self, message_id: int) -> None:
        """Сохранить message_id (игнорирует дубликаты)."""
        # Проверяем существует ли уже
        result = await self.supabase.table("commands_messages") \
            .select("id") \
            .eq("message_id", message_id) \
            .limit(1) \
            .execute()

        if not result.data:
            await self.supabase.table("commands_messages") \
                .insert({"message_id": message_id}) \
                .execute()
            logger.debug(f"💾 Saved message_id: {message_id}")

    async def get_all(self) -> list[int]:
        """Получить все сохранённые message_id."""
        result = await self.supabase.table("commands_messages") \
            .select("message_id") \
            .order("message_id") \
            .execute()
        message_ids = [row["message_id"] for row in result.data]
        logger.debug(f"📋 All message_ids: {message_ids}")
        return message_ids

    async def delete_all(self) -> None:
        """Удалить все записи."""
        await self.supabase.table("commands_messages") \
            .delete() \
            .neq("id", 0) \
            .execute()
        logger.debug("🗑️ Deleted all commands_messages")