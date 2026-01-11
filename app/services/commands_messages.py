"""Сервис для хранения ID сообщений в топике Команды."""

import logging
from supabase.client import AsyncClient

logger = logging.getLogger(__name__)


class CommandsMessagesService:
    def __init__(self, supabase: AsyncClient, bot_type: str):
        self.supabase = supabase
        self.bot_type = bot_type

    async def add(self, message_id: int) -> None:
        """Сохранить message_id (игнорирует дубликаты)."""
        # Проверяем существует ли уже
        result = await self.supabase.table("commands_messages") \
            .select("id") \
            .eq("message_id", message_id) \
            .eq("bot_type", self.bot_type) \
            .limit(1) \
            .execute()

        if not result.data:
            await self.supabase.table("commands_messages") \
                .insert({"message_id": message_id, "bot_type": self.bot_type}) \
                .execute()
            logger.debug(f"💾 Saved message_id: {message_id} (bot_type={self.bot_type})")

    async def get_all(self) -> list[int]:
        """Получить все сохранённые message_id для этого бота."""
        result = await self.supabase.table("commands_messages") \
            .select("message_id") \
            .eq("bot_type", self.bot_type) \
            .order("message_id") \
            .execute()
        message_ids = [row["message_id"] for row in result.data]
        logger.debug(f"📋 All message_ids for {self.bot_type}: {message_ids}")
        return message_ids

    async def delete_all(self) -> None:
        """Удалить все записи для этого бота."""
        await self.supabase.table("commands_messages") \
            .delete() \
            .eq("bot_type", self.bot_type) \
            .execute()
        logger.debug(f"🗑️ Deleted all commands_messages for {self.bot_type}")