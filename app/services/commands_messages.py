"""Сервис для хранения ID сообщений в топике Команды."""

from supabase.client import AsyncClient


class CommandsMessagesService:
    def __init__(self, supabase: AsyncClient):
        self.supabase = supabase

    async def add(self, message_id: int) -> None:
        """Сохранить message_id."""
        await self.supabase.table("commands_messages") \
            .insert({"message_id": message_id}) \
            .execute()

    async def get_all(self) -> list[int]:
        """Получить все сохранённые message_id."""
        result = await self.supabase.table("commands_messages") \
            .select("message_id") \
            .execute()
        return [row["message_id"] for row in result.data]

    async def delete_all(self) -> None:
        """Удалить все записи."""
        await self.supabase.table("commands_messages") \
            .delete() \
            .neq("id", 0) \
            .execute()