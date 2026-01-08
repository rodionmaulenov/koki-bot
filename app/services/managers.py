"""Сервис для работы с менеджерами."""

from supabase import AsyncClient


class ManagerService:
    """Работает с таблицей managers."""

    def __init__(self, supabase: AsyncClient):
        self.supabase = supabase

    async def get_by_telegram_id(self, telegram_id: int) -> dict | None:
        """Получить менеджера по telegram_id."""
        result = await self.supabase.table("managers") \
            .select("*") \
            .eq("telegram_id", telegram_id) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def get_by_id(self, manager_id: int) -> dict | None:
        """Получить менеджера по id."""
        result = await self.supabase.table("managers") \
            .select("*") \
            .eq("id", manager_id) \
            .execute()

        if result.data:
            return result.data[0]
        return None