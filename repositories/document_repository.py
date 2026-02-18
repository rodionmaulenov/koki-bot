from supabase import AsyncClient

from models.document import Document


class DocumentRepository:
    def __init__(self, supabase: AsyncClient) -> None:
        self._supabase = supabase

    async def get_by_user_id(self, user_id: int) -> Document | None:
        response = await (
            self._supabase.schema("kok")
            .table("documents")
            .select(
                "id, user_id, manager_id, passport_file_id, receipt_file_id,"
                " receipt_price, card_file_id, card_number, card_holder_name, created_at",
            )
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return Document(**response.data[0])
        return None
