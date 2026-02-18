from supabase import AsyncClient

from models.user import User


class UserRepository:
    def __init__(self, supabase: AsyncClient) -> None:
        self._supabase = supabase

    async def get_by_id(self, user_id: int) -> User | None:
        response = await (
            self._supabase.schema("kok")
            .table("users")
            .select("id, telegram_id, name, manager_id, topic_id, created_at")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return User(**response.data[0])
        return None

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        response = await (
            self._supabase.schema("kok")
            .table("users")
            .select("id, telegram_id, name, manager_id, topic_id, created_at")
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return User(**response.data[0])
        return None

    async def get_by_manager_id(self, manager_id: int) -> list[User]:
        response = await (
            self._supabase.schema("kok")
            .table("users")
            .select("id, telegram_id, name, manager_id, topic_id, created_at")
            .eq("manager_id", manager_id)
            .execute()
        )
        return [User(**row) for row in response.data]

    async def get_by_name_prefix_and_birth_date(
        self, last_name: str, first_name: str, birth_date: str,
    ) -> User | None:
        response = await (
            self._supabase.schema("kok")
            .table("users")
            .select("id, telegram_id, name, manager_id, topic_id, created_at")
            .ilike("name", f"{last_name} {first_name}%")
            .eq("birth_date", birth_date)
            .limit(1)
            .execute()
        )
        if response.data:
            return User(**response.data[0])
        return None

    async def set_telegram_id(self, user_id: int, telegram_id: int) -> None:
        await (
            self._supabase.schema("kok")
            .table("users")
            .update({"telegram_id": telegram_id})
            .eq("id", user_id)
            .execute()
        )

    async def get_with_topic(self) -> list[User]:
        """Get all users that have a forum topic (topic_id IS NOT NULL)."""
        response = await (
            self._supabase.schema("kok")
            .table("users")
            .select("id, telegram_id, name, manager_id, topic_id, created_at")
            .not_.is_("topic_id", "null")
            .execute()
        )
        return [User(**row) for row in response.data]

    async def clear_topic_id(self, user_id: int) -> None:
        await (
            self._supabase.schema("kok")
            .table("users")
            .update({"topic_id": None})
            .eq("id", user_id)
            .execute()
        )

    async def set_topic_id(self, user_id: int, topic_id: int) -> None:
        await (
            self._supabase.schema("kok")
            .table("users")
            .update({"topic_id": topic_id})
            .eq("id", user_id)
            .execute()
        )
