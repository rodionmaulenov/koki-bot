from supabase import AsyncClient

from models.manager import Manager


class ManagerRepository:
    def __init__(self, supabase: AsyncClient) -> None:
        self._supabase = supabase

    async def get_by_id(self, manager_id: int) -> Manager | None:
        response = await (
            self._supabase.schema("public")
            .table("managers")
            .select("id, telegram_id, name, is_active, created_at")
            .eq("id", manager_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return Manager(**response.data[0])
        return None

    async def get_by_telegram_id(self, telegram_id: int) -> Manager | None:
        response = await (
            self._supabase.schema("public")
            .table("managers")
            .select("id, telegram_id, name, is_active, created_at")
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return Manager(**response.data[0])
        return None
