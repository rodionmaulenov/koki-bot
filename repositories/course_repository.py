from datetime import date, datetime, time

from supabase import AsyncClient

from models.course import Course
from models.enums import RemovalReason

_SELECT_COLUMNS = (
    "id, user_id, status, invite_code, invite_used, "
    "cycle_day, intake_time, start_date, current_day, total_days, "
    "late_count, late_dates, appeal_count, appeal_video, appeal_text, "
    "extended, registration_message_id, removal_reason, appeal_deadline, "
    "created_at, updated_at"
)


class CourseRepository:
    def __init__(self, supabase: AsyncClient) -> None:
        self._supabase = supabase

    async def get_by_id(self, course_id: int) -> Course | None:
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .select(_SELECT_COLUMNS)
            .eq("id", course_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return Course(**response.data[0])

    async def get_by_invite_code(self, invite_code: str) -> Course | None:
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .select("id, user_id, status, invite_code, invite_used, created_at")
            .eq("invite_code", invite_code)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return Course(**response.data[0])

    async def get_active_by_user_id(self, user_id: int) -> Course | None:
        """Find course with non-terminal status (setup/active/appeal)."""
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .select(_SELECT_COLUMNS)
            .eq("user_id", user_id)
            .in_("status", ["setup", "active", "appeal"])
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return Course(**response.data[0])

    async def set_expired(self, course_id: int) -> None:
        await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"status": "expired"})
            .eq("id", course_id)
            .execute()
        )

    async def set_expired_batch(self, course_ids: list[int]) -> None:
        if not course_ids:
            return
        await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"status": "expired"})
            .in_("id", course_ids)
            .execute()
        )

    async def get_reissuable_by_user_ids(
        self, user_ids: list[int], *, cutoff: datetime,
    ) -> list[Course]:
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .select("id, user_id, status, invite_code, created_at")
            .in_("user_id", user_ids)
            .in_("status", ["setup", "expired"])
            .gte("created_at", cutoff.isoformat())
            .order("created_at", desc=True)
            .execute()
        )
        return [Course(**row) for row in response.data]

    async def activate(
        self,
        course_id: int,
        cycle_day: int,
        intake_time: time,
        start_date: date,
    ) -> bool:
        """Activate course. Returns False if already activated (race condition)."""
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .update({
                "cycle_day": cycle_day,
                "intake_time": intake_time.isoformat(),
                "start_date": start_date.isoformat(),
                "status": "active",
                "invite_used": True,
            })
            .eq("id", course_id)
            .eq("status", "setup")
            .execute()
        )
        return bool(response.data)

    async def set_registration_message_id(
        self,
        course_id: int,
        message_id: int,
    ) -> None:
        await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"registration_message_id": message_id})
            .eq("id", course_id)
            .execute()
        )

    async def update_current_day(self, course_id: int, new_day: int) -> None:
        """Set current_day to a specific value."""
        await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"current_day": new_day})
            .eq("id", course_id)
            .execute()
        )

    async def record_late(
        self, course_id: int, late_count: int, late_dates: list[str],
    ) -> None:
        """Update late_count and late_dates atomically."""
        await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"late_count": late_count, "late_dates": late_dates})
            .eq("id", course_id)
            .execute()
        )

    async def set_completed(self, course_id: int) -> None:
        """Unconditional completion. DEPRECATED: use complete_course_active() instead."""
        await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"status": "completed"})
            .eq("id", course_id)
            .execute()
        )

    async def set_refused(
        self, course_id: int, removal_reason: str | None = None,
        appeal_deadline: datetime | None = None,
    ) -> None:
        update_data: dict = {"status": "refused"}
        if removal_reason:
            update_data["removal_reason"] = removal_reason
        if appeal_deadline:
            update_data["appeal_deadline"] = appeal_deadline.isoformat()
        await (
            self._supabase.schema("kok")
            .table("courses")
            .update(update_data)
            .eq("id", course_id)
            .execute()
        )

    async def reissue(self, course_id: int, invite_code: str) -> Course:
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .update({
                "invite_code": invite_code,
                "invite_used": False,
                "status": "setup",
                "cycle_day": None,
                "intake_time": None,
                "start_date": None,
                "current_day": 0,
            })
            .eq("id", course_id)
            .execute()
        )
        if not response.data:
            msg = f"Course not found: course_id={course_id}"
            raise RuntimeError(msg)
        return Course(**response.data[0])

    # ── Appeal (Phase 5) ──

    async def start_appeal(self, course_id: int) -> bool:
        """Set course status refused → appeal. Returns False on race condition."""
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"status": "appeal", "appeal_deadline": None})
            .eq("id", course_id)
            .eq("status", "refused")
            .execute()
        )
        return bool(response.data)

    async def save_appeal_data(
        self, course_id: int, appeal_video: str, appeal_text: str,
    ) -> None:
        """Save appeal video file_id and text."""
        await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"appeal_video": appeal_video, "appeal_text": appeal_text})
            .eq("id", course_id)
            .execute()
        )

    async def accept_appeal(self, course_id: int, new_appeal_count: int) -> bool:
        """Accept appeal: status appeal → active, update appeal_count.

        Returns False on race condition (already handled).
        """
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .update({
                "status": "active",
                "appeal_count": new_appeal_count,
                "removal_reason": None,
                "appeal_deadline": None,
            })
            .eq("id", course_id)
            .eq("status", "appeal")
            .execute()
        )
        return bool(response.data)

    async def decline_appeal(
        self, course_id: int, new_appeal_count: int,
        removal_reason: str | None = RemovalReason.APPEAL_DECLINED,
    ) -> bool:
        """Decline appeal: status appeal → refused, update appeal_count.

        Returns False on race condition (already handled).
        """
        update_data: dict = {
            "status": "refused",
            "appeal_count": new_appeal_count,
        }
        if removal_reason:
            update_data["removal_reason"] = removal_reason
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .update(update_data)
            .eq("id", course_id)
            .eq("status", "appeal")
            .execute()
        )
        return bool(response.data)

    # ── Card buttons (Phase 5) ──

    async def complete_course_active(self, course_id: int) -> bool:
        """Complete course from active status only.

        Returns False if not active (race condition with late removal).
        """
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"status": "completed"})
            .eq("id", course_id)
            .eq("status", "active")
            .execute()
        )
        return bool(response.data)

    # ── Workers (Phase 4) ──

    async def get_active_in_intake_window(
        self, today: str, time_from: str, time_to: str,
    ) -> list[Course]:
        """Get active courses with intake_time in [time_from, time_to].

        Used by workers to find courses needing reminders/alerts.
        """
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .select(_SELECT_COLUMNS)
            .eq("status", "active")
            .lte("start_date", today)
            .gte("intake_time", time_from)
            .lte("intake_time", time_to)
            .execute()
        )
        return [Course(**row) for row in response.data]

    async def get_appeal_courses(self) -> list[Course]:
        """Get all courses in appeal status (for deadline check)."""
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .select(_SELECT_COLUMNS)
            .eq("status", "appeal")
            .execute()
        )
        return [Course(**row) for row in response.data]

    async def get_ended_user_ids(
        self, user_ids: list[int], before: datetime,
    ) -> set[int]:
        """Get user_ids whose course ended (refused/completed) before cutoff."""
        if not user_ids:
            return set()
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .select("user_id")
            .in_("user_id", user_ids)
            .in_("status", ["refused", "completed"])
            .lt("updated_at", before.isoformat())
            .execute()
        )
        return {row["user_id"] for row in response.data}

    async def refuse_if_active(
        self, course_id: int, removal_reason: str | None = None,
        appeal_deadline: datetime | None = None,
    ) -> bool:
        """Refuse course only if currently active. Returns False if not active."""
        update_data: dict = {"status": "refused"}
        if removal_reason:
            update_data["removal_reason"] = removal_reason
        if appeal_deadline:
            update_data["appeal_deadline"] = appeal_deadline.isoformat()
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .update(update_data)
            .eq("id", course_id)
            .eq("status", "active")
            .execute()
        )
        return bool(response.data)

    async def refuse_if_appeal(
        self, course_id: int, new_appeal_count: int,
        removal_reason: str | None = RemovalReason.APPEAL_EXPIRED,
    ) -> bool:
        """Auto-refuse appeal (deadline expired). Returns False if not in appeal."""
        update_data: dict = {
            "status": "refused",
            "appeal_count": new_appeal_count,
        }
        if removal_reason:
            update_data["removal_reason"] = removal_reason
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .update(update_data)
            .eq("id", course_id)
            .eq("status", "appeal")
            .execute()
        )
        return bool(response.data)

    async def get_refused_with_expired_appeal(
        self, now: datetime,
    ) -> list[Course]:
        """Get refused courses where appeal_deadline has passed."""
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .select(_SELECT_COLUMNS)
            .eq("status", "refused")
            .lt("appeal_deadline", now.isoformat())
            .execute()
        )
        return [Course(**row) for row in response.data]

    async def extend_course(self, course_id: int, new_total: int) -> bool:
        """Extend course: total_days → new_total, extended = True.

        Returns False if already extended or not active (race condition).
        """
        response = await (
            self._supabase.schema("kok")
            .table("courses")
            .update({"total_days": new_total, "extended": True})
            .eq("id", course_id)
            .eq("status", "active")
            .eq("extended", False)
            .execute()
        )
        return bool(response.data)
