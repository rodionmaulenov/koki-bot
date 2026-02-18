from supabase import AsyncClient

from models.owner import Owner


class OwnerRepository:
    def __init__(self, supabase: AsyncClient) -> None:
        self._supabase = supabase

    async def get_by_telegram_id(self, telegram_id: int) -> Owner | None:
        response = await (
            self._supabase.schema("public")
            .table("owners")
            .select("id, telegram_id, name, is_active, created_at")
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return Owner(**response.data[0])
        return None
