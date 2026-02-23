import logging
from datetime import datetime, timedelta
from enum import StrEnum

from models.course import Course
from models.enums import RemovalReason
from models.intake_log import IntakeLog
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from utils.time import TASHKENT_TZ, get_tashkent_now

logger = logging.getLogger(__name__)

WINDOW_BEFORE_MINUTES = 10
WINDOW_AFTER_MINUTES = 120
AI_CONFIDENCE_THRESHOLD = 0.85
DEADLINE_HOURS_BEFORE = 2
LATE_THRESHOLD_MINUTES = 30
BASE_MAX_STRIKES = 3


class WindowStatus(StrEnum):
    EARLY = "early"
    OPEN = "open"
    CLOSED = "closed"


class VideoService:
    def __init__(
        self,
        course_repository: CourseRepository,
        intake_log_repository: IntakeLogRepository,
    ) -> None:
        self._course_repo = course_repository
        self._intake_log_repo = intake_log_repository

    def check_window(self, course: Course) -> tuple[WindowStatus, str]:
        """Check if current time is within the intake window.

        Handles midnight crossing: intake_time=23:30 → window 23:20—01:30.
        Returns (status, open_time_hint).
        """
        if course.intake_time is None:
            return WindowStatus.CLOSED, ""

        now = get_tashkent_now()
        today = now.date()

        scheduled_today = datetime.combine(today, course.intake_time, tzinfo=TASHKENT_TZ)

        # Check today's window
        today_start = scheduled_today - timedelta(minutes=WINDOW_BEFORE_MINUTES)
        today_end = scheduled_today + timedelta(minutes=WINDOW_AFTER_MINUTES)

        if today_start <= now <= today_end:
            return WindowStatus.OPEN, ""

        # Check yesterday's window (midnight crossing: e.g. 23:30 → window until 01:30)
        yesterday_scheduled = scheduled_today - timedelta(days=1)
        yesterday_end = yesterday_scheduled + timedelta(minutes=WINDOW_AFTER_MINUTES)

        if now <= yesterday_end:
            return WindowStatus.OPEN, ""

        # Not in any window
        if now < today_start:
            open_time = today_start.strftime("%H:%M")
            return WindowStatus.EARLY, open_time

        return WindowStatus.CLOSED, ""

    async def get_today_log(self, course: Course) -> IntakeLog | None:
        """Get intake log for today (current_day + 1)."""
        next_day = course.current_day + 1
        return await self._intake_log_repo.get_by_course_and_day(course.id, next_day)

    async def record_intake(
        self,
        course: Course,
        video_file_id: str,
        approved: bool,
        confidence: float,
    ) -> IntakeLog:
        """Record video intake and update course progress.

        Returns created IntakeLog.
        """
        now = get_tashkent_now()
        today = now.date()
        next_day = course.current_day + 1

        if course.intake_time is None:
            scheduled = now
        else:
            scheduled_today = datetime.combine(
                today, course.intake_time, tzinfo=TASHKENT_TZ,
            )
            today_start = scheduled_today - timedelta(minutes=WINDOW_BEFORE_MINUTES)
            # If now is before today's window start, we're in yesterday's window
            # (midnight crossing: e.g. intake 23:30, now 00:15)
            if now < today_start:
                scheduled = scheduled_today - timedelta(days=1)
            else:
                scheduled = scheduled_today

        delay_minutes: int | None = None
        taken_delta = now - scheduled
        if taken_delta.total_seconds() > 0:
            delay_minutes = int(taken_delta.total_seconds() / 60)

        if approved:
            status = "taken"
            verified_by = "gemini"
        else:
            status = "pending_review"
            verified_by = None

        intake_log = await self._intake_log_repo.create(
            course_id=course.id,
            day=next_day,
            scheduled_at=scheduled,
            taken_at=now,
            status=status,
            video_file_id=video_file_id,
            delay_minutes=delay_minutes,
            verified_by=verified_by,
            confidence=confidence,
        )

        if approved:
            await self._course_repo.update_current_day(course.id, next_day)
            logger.info(
                "Day %d/%d recorded for course_id=%d (AI approved, confidence=%.2f)",
                next_day, course.total_days, course.id, confidence,
            )
        else:
            logger.info(
                "Day %d pending review for course_id=%d (confidence=%.2f)",
                next_day, course.id, confidence,
            )

        return intake_log

    async def save_private_message_id(
        self, log_id: int, private_message_id: int,
    ) -> None:
        """Save the girl's private chat message ID for later editing."""
        await self._intake_log_repo.set_private_message_id(log_id, private_message_id)

    async def confirm_intake(self, log_id: int, course_id: int, day: int) -> bool:
        """Manager confirmed the video. Mark as taken, advance day.

        Returns False if already handled (race condition).
        """
        updated = await self._intake_log_repo.update_status(
            log_id, "taken", verified_by="manager",
            expected_status="pending_review",
        )
        if not updated:
            return False
        await self._course_repo.update_current_day(course_id, day)
        logger.info(
            "Day %d confirmed by manager for course_id=%d",
            day, course_id,
        )
        return True

    async def reject_intake(self, log_id: int, course_id: int) -> bool:
        """Manager rejected the video. Mark as rejected, refuse course.

        Returns False if already handled (race condition).
        """
        updated = await self._intake_log_repo.update_status(
            log_id, "rejected", expected_status="pending_review",
        )
        if not updated:
            return False
        await self._course_repo.set_refused(course_id, removal_reason=RemovalReason.MANAGER_REJECT)
        logger.info(
            "Video rejected by manager for course_id=%d, log_id=%d",
            course_id, log_id,
        )
        return True

    # ── Course completion ──

    async def complete_course(self, course_id: int) -> bool:
        """Mark course as completed (only if still active).

        Returns False if course is no longer active (race with worker removal).
        """
        completed = await self._course_repo.complete_course_active(course_id)
        if completed:
            logger.info("Course completed: course_id=%d", course_id)
        else:
            logger.warning("Course not completed (no longer active): course_id=%d", course_id)
        return completed

    # ── Reshoot (Phase 2.3) ──

    def calculate_deadline(self, course: Course) -> datetime:
        """Calculate reshoot/review deadline: tomorrow + intake_time - 2h."""
        now = get_tashkent_now()
        tomorrow = now.date() + timedelta(days=1)
        intake = course.intake_time or now.time()
        scheduled = datetime.combine(tomorrow, intake, tzinfo=TASHKENT_TZ)
        return scheduled - timedelta(hours=DEADLINE_HOURS_BEFORE)

    async def request_reshoot(self, log_id: int, course: Course) -> datetime:
        """Manager requested reshoot. Set status and deadline. Returns deadline."""
        deadline = self.calculate_deadline(course)
        await self._intake_log_repo.set_reshoot(log_id, deadline)
        logger.info(
            "Reshoot requested for log_id=%d, deadline=%s",
            log_id, deadline.isoformat(),
        )
        return deadline

    async def get_pending_reshoot(self, course_id: int) -> IntakeLog | None:
        """Find intake_log with status 'reshoot' for this course."""
        return await self._intake_log_repo.get_by_course_and_status(
            course_id, "reshoot",
        )

    async def expire_reshoot(self, log_id: int, course_id: int) -> None:
        """Reshoot deadline expired. Mark as missed, refuse course."""
        await self._intake_log_repo.update_status(log_id, "missed")
        await self._course_repo.set_refused(course_id, removal_reason=RemovalReason.RESHOOT_EXPIRED)
        logger.info(
            "Reshoot expired for log_id=%d, course_id=%d — course refused",
            log_id, course_id,
        )

    async def accept_reshoot(
        self, log_id: int, course_id: int, day: int,
        video_file_id: str, confidence: float, verified_by: str,
    ) -> None:
        """Reshoot video approved. Update existing log, advance day."""
        now = get_tashkent_now()
        await self._intake_log_repo.update_after_reshoot(
            log_id=log_id,
            status="taken",
            video_file_id=video_file_id,
            taken_at=now,
            confidence=confidence,
            verified_by=verified_by,
        )
        await self._course_repo.update_current_day(course_id, day)
        logger.info(
            "Reshoot accepted for log_id=%d, day %d, course_id=%d",
            log_id, day, course_id,
        )

    async def reshoot_pending_review(
        self, log_id: int, video_file_id: str, confidence: float,
    ) -> None:
        """Reshoot video uncertain. Update log, send to manager again."""
        now = get_tashkent_now()
        await self._intake_log_repo.update_after_reshoot(
            log_id=log_id,
            status="pending_review",
            video_file_id=video_file_id,
            taken_at=now,
            confidence=confidence,
            verified_by=None,
        )

    # ── Late strikes (Phase 3) ──

    def get_max_strikes(self, course: Course) -> int:
        """Dynamic threshold: 3 + appeal_count (each accepted appeal adds +1)."""
        return BASE_MAX_STRIKES + course.appeal_count

    async def record_late(self, course: Course) -> tuple[int, list[str]]:
        """Record a late strike. Returns (new_late_count, updated_late_dates)."""
        now = get_tashkent_now()
        new_count = course.late_count + 1
        new_dates = [*course.late_dates, now.isoformat()]
        await self._course_repo.record_late(course.id, new_count, new_dates)
        logger.info(
            "Late strike %d recorded for course_id=%d",
            new_count, course.id,
        )
        return new_count, new_dates

    async def undo_day_and_refuse(
        self, course_id: int, original_day: int,
        appeal_deadline: datetime | None = None,
    ) -> None:
        """3rd strike: undo day increment, refuse course."""
        await self._course_repo.update_current_day(course_id, original_day)
        await self._course_repo.set_refused(
            course_id, removal_reason=RemovalReason.MAX_STRIKES,
            appeal_deadline=appeal_deadline,
        )
        logger.info(
            "Final strike: undid day, refused course_id=%d", course_id,
        )