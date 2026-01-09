"""Сервис для работы с пользователями."""

from supabase import AsyncClient


class UserService:
    """Работает с таблицей users."""

    def __init__(self, supabase: AsyncClient):
        self.supabase = supabase

    async def create(self, name: str, manager_id: int) -> dict:
        """Создать пользователя (без telegram_id — добавится позже)."""
        result = await self.supabase.table("users") \
            .insert({
                "name": name,
                "manager_id": manager_id,
            }) \
            .execute()

        return result.data[0] if result.data else {}

    async def get_by_id(self, user_id: int) -> dict | None:
        """Получить пользователя по id."""
        result = await self.supabase.table("users") \
            .select("*") \
            .eq("id", user_id) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def set_telegram_id(self, user_id: int, telegram_id: int) -> None:
        """Установить telegram_id пользователю."""
        # Сначала очищаем telegram_id у других юзеров (если был привязан ранее)
        await self.supabase.table("users") \
            .update({"telegram_id": None}) \
            .eq("telegram_id", telegram_id) \
            .neq("id", user_id) \
            .execute()

        # Устанавливаем telegram_id текущему юзеру
        await self.supabase.table("users") \
            .update({"telegram_id": telegram_id}) \
            .eq("id", user_id) \
            .execute()

    async def get_by_telegram_id(self, telegram_id: int) -> dict | None:
        """Получить пользователя по telegram_id."""
        result = await self.supabase.table("users") \
            .select("*") \
            .eq("telegram_id", telegram_id) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def set_topic_id(self, user_id: int, topic_id: int) -> None:
        """Установить topic_id пользователю."""
        await self.supabase.table("users") \
            .update({"topic_id": topic_id}) \
            .eq("id", user_id) \
            .execute()

    async def get_by_name_and_manager(self, name: str, manager_id: int) -> dict | None:
        """Найти пользователя по имени и менеджеру."""
        result = await self.supabase.table("users") \
            .select("*") \
            .eq("name", name) \
            .eq("manager_id", manager_id) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()

        return result.data[0] if result.data else None

    async def get_telegram_id(self, user_id: int) -> int | None:
        """Получить telegram_id пользователя."""
        result = await self.supabase.table("users") \
            .select("telegram_id") \
            .eq("id", user_id) \
            .single() \
            .execute()

        return result.data.get("telegram_id") if result.data else None

    async def get_active_by_manager(self, manager_id: int) -> list[dict]:
        """Получить список девушек менеджера с активными курсами."""
        result = await self.supabase.table("users") \
            .select("name, courses(status)") \
            .eq("manager_id", manager_id) \
            .execute()

        # Фильтруем только тех у кого есть активный курс
        active_users = []
        for user in result.data or []:
            courses = user.get("courses") or []
            if any(c.get("status") == "active" for c in courses):
                active_users.append(user)

        return active_users