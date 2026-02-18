from datetime import datetime

from supabase import AsyncClient

from models.intake_log import IntakeLog


class IntakeLogRepository:
    _SELECT_COLUMNS = (
        "id, course_id, day, scheduled_at, taken_at, status, "
        "delay_minutes, video_file_id, verified_by, confidence, "
        "review_started_at, reshoot_deadline, private_message_id, created_at"
    )

    def __init__(self, supabase: AsyncClient) -> None:
        self._supabase = supabase

    async def create(
        self,
        course_id: int,
        day: int,
        scheduled_at: datetime,
        taken_at: datetime,
        status: str,
        video_file_id: str,
        delay_minutes: int | None = None,
        verified_by: str | None = None,
        confidence: float | None = None,
    ) -> IntakeLog:
        data: dict[str, object] = {
            "course_id": course_id,
            "day": day,
            "scheduled_at": scheduled_at.isoformat(),
            "taken_at": taken_at.isoformat(),
            "status": status,
            "video_file_id": video_file_id,
        }
        if delay_minutes is not None:
            data["delay_minutes"] = delay_minutes
        if verified_by is not None:
            data["verified_by"] = verified_by
        if confidence is not None:
            data["confidence"] = confidence
        if status == "pending_review":
            data["review_started_at"] = taken_at.isoformat()

        response = await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .insert(data)
            .execute()
        )
        return IntakeLog(**response.data[0])

    async def get_by_course_and_day(
        self, course_id: int, day: int,
    ) -> IntakeLog | None:
        response = await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .select(self._SELECT_COLUMNS)
            .eq("course_id", course_id)
            .eq("day", day)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return IntakeLog(**response.data[0])

    async def get_by_id(self, log_id: int) -> IntakeLog | None:
        response = await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .select(self._SELECT_COLUMNS)
            .eq("id", log_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return IntakeLog(**response.data[0])

    async def update_status(
        self,
        log_id: int,
        status: str,
        verified_by: str | None = None,
        expected_status: str | None = None,
    ) -> bool:
        """Update log status. If expected_status given, only update when current
        status matches (atomic). Returns True if row was updated."""
        data: dict[str, object] = {"status": status}
        if verified_by is not None:
            data["verified_by"] = verified_by
        query = (
            self._supabase.schema("kok")
            .table("intake_logs")
            .update(data)
            .eq("id", log_id)
        )
        if expected_status is not None:
            query = query.eq("status", expected_status)
        response = await query.execute()
        return bool(response.data)

    async def set_private_message_id(
        self, log_id: int, private_message_id: int,
    ) -> None:
        await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .update({"private_message_id": private_message_id})
            .eq("id", log_id)
            .execute()
        )

    async def set_reshoot(self, log_id: int, deadline: datetime) -> None:
        """Set status to 'reshoot' with deadline."""
        await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .update({
                "status": "reshoot",
                "reshoot_deadline": deadline.isoformat(),
            })
            .eq("id", log_id)
            .execute()
        )

    async def get_by_course_and_status(
        self, course_id: int, status: str,
    ) -> IntakeLog | None:
        """Find single intake_log by course and status."""
        response = await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .select(self._SELECT_COLUMNS)
            .eq("course_id", course_id)
            .eq("status", status)
            .order("day", desc=True)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return IntakeLog(**response.data[0])

    # ── Workers (Phase 4) ──

    async def has_log_today(self, course_id: int, day: int) -> bool:
        """Check if intake_log exists for this course and day."""
        response = await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .select("id")
            .eq("course_id", course_id)
            .eq("day", day)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    async def get_pending_reviews_with_start(self) -> list[IntakeLog]:
        """Get all pending_review logs that have review_started_at set."""
        response = await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .select(self._SELECT_COLUMNS)
            .eq("status", "pending_review")
            .not_.is_("review_started_at", "null")
            .execute()
        )
        return [IntakeLog(**row) for row in response.data]

    async def get_expired_reshoots(self, now: str) -> list[IntakeLog]:
        """Get reshoot logs where reshoot_deadline < now (expired)."""
        response = await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .select(self._SELECT_COLUMNS)
            .eq("status", "reshoot")
            .lt("reshoot_deadline", now)
            .execute()
        )
        return [IntakeLog(**row) for row in response.data]

    async def update_after_reshoot(
        self,
        log_id: int,
        status: str,
        video_file_id: str,
        taken_at: datetime,
        confidence: float,
        verified_by: str | None = None,
    ) -> None:
        """Update existing intake_log with new reshoot video data."""
        data: dict[str, object] = {
            "status": status,
            "video_file_id": video_file_id,
            "taken_at": taken_at.isoformat(),
            "confidence": confidence,
        }
        if verified_by is not None:
            data["verified_by"] = verified_by
        if status == "pending_review":
            data["review_started_at"] = taken_at.isoformat()
        await (
            self._supabase.schema("kok")
            .table("intake_logs")
            .update(data)
            .eq("id", log_id)
            .execute()
        )
