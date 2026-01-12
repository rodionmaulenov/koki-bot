"""Сервис для работы с таблицей intake_logs."""

from supabase import AsyncClient


class IntakeLogsService:
    """Работает с таблицей intake_logs — записи о приёме таблеток."""

    def __init__(self, supabase: AsyncClient):
        self.supabase = supabase

    async def get_by_course_and_day(self, course_id: int, day: int) -> dict | None:
        """Получить запись по course_id и дню."""
        result = await self.supabase.table("intake_logs") \
            .select("*") \
            .eq("course_id", course_id) \
            .eq("day", day) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    async def create(
            self,
            course_id: int,
            day: int,
            status: str,
            video_file_id: str,
            verified_by: str | None = None,
            confidence: float | None = None,
    ) -> dict:
        """Создать запись о приёме."""
        result = await self.supabase.table("intake_logs") \
            .insert({
            "course_id": course_id,
            "day": day,
            "status": status,
            "video_file_id": video_file_id,
            "verified_by": verified_by,
            "confidence": confidence,
        }) \
            .execute()

        return result.data[0] if result.data else {}

    async def update_status(
            self,
            course_id: int,
            day: int,
            status: str,
            verified_by: str | None = None,
    ) -> None:
        """Обновить статус записи."""
        data = {"status": status}
        if verified_by:
            data["verified_by"] = verified_by

        await self.supabase.table("intake_logs") \
            .update(data) \
            .eq("course_id", course_id) \
            .eq("day", day) \
            .execute()

    async def has_log_today(self, course_id: int) -> bool:
        """Проверяет, есть ли intake_log сегодня (по Ташкентскому времени)."""
        from datetime import timezone
        from app.utils.time_utils import get_tashkent_now

        # Полночь сегодня по Ташкенту → в UTC
        tashkent_midnight = get_tashkent_now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        utc_start = tashkent_midnight.astimezone(timezone.utc).isoformat()

        result = await self.supabase.table("intake_logs") \
            .select("id") \
            .eq("course_id", course_id) \
            .gte("created_at", utc_start) \
            .limit(1) \
            .execute()

        return bool(result.data)
