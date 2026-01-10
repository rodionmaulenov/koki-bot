"""Сервис для работы с курсами."""

from supabase import AsyncClient


class CourseService:
    """Работает с таблицей courses."""

    def __init__(self, supabase: AsyncClient):
        self.supabase = supabase

    async def create(self, user_id: int, invite_code: str) -> dict:
        """Создать курс. Проверяет что нет активного."""

        # Проверяем существующий курс
        existing = await self.get_active_by_user_id(user_id)

        if existing:
            status = existing.get("status")
            invite_used = existing.get("invite_used", False)

            # Setup с неиспользованной ссылкой — возвращаем его
            if status == "setup" and not invite_used:
                return existing

            # Active — нельзя создавать новый
            if status == "active":
                raise ValueError("User already has active course")

        # Создаём новый курс
        result = await self.supabase.table("courses") \
            .insert({
            "user_id": user_id,
            "invite_code": invite_code,
            "status": "setup",
        }) \
            .execute()

        return result.data[0] if result.data else {}

    async def get_by_invite_code(self, invite_code: str) -> dict | None:
        """Найти курс по invite_code."""
        result = await self.supabase.table("courses") \
            .select("*") \
            .eq("invite_code", invite_code) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def mark_invite_used(self, course_id: int) -> None:
        """Отметить ссылку как использованную."""
        await self.supabase.table("courses") \
            .update({"invite_used": True}) \
            .eq("id", course_id) \
            .execute()

    async def get_active_by_user_id(self, user_id: int) -> dict | None:
        """Найти активный курс пользователя."""
        result = await self.supabase.table("courses") \
            .select("*") \
            .eq("user_id", user_id) \
            .in_("status", ["setup", "active"]) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def update(self, course_id: int, **kwargs) -> None:
        """Обновить курс."""
        await self.supabase.table("courses") \
            .update(kwargs) \
            .eq("id", course_id) \
            .execute()

    async def get_by_id(self, course_id: int) -> dict | None:
        """Получить курс по id."""
        result = await self.supabase.table("courses") \
            .select("*") \
            .eq("id", course_id) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def get_active_started(self, today: str) -> list[dict]:
        """Получить активные курсы которые уже начались."""
        result = await self.supabase.table("courses") \
            .select("id, user_id, current_day, late_count, intake_time") \
            .eq("status", "active") \
            .lte("start_date", today) \
            .execute()

        return result.data or []

    async def set_refused(self, course_id: int) -> None:
        """Завершить курс отказом."""
        await self.supabase.table("courses") \
            .update({"status": "refused"}) \
            .eq("id", course_id) \
            .execute()

    async def set_expired(self, course_id: int) -> None:
        """Завершить курс как истёкший (не завершила регистрацию вовремя)."""
        await self.supabase.table("courses") \
            .update({"status": "expired"}) \
            .eq("id", course_id) \
            .execute()