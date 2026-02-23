"""Tests for VideoService — unit tests with mocked dependencies.

Key logic tested:
- Intake window with midnight crossing (23:30 → 01:30)
- Delay calculation (positive, zero, negative)
- Correct argument passing to repositories
- Strike calculation with appeal bonus
"""
from datetime import datetime, time
from unittest.mock import AsyncMock

from models.course import Course
from models.enums import CourseStatus, RemovalReason
from models.intake_log import IntakeLog
from services.video_service import VideoService, WindowStatus
from utils.time import TASHKENT_TZ


# =============================================================================
# HELPERS
# =============================================================================


def make_course(**overrides) -> Course:
    """Create a Course model object for testing (no DB)."""
    defaults = {
        "id": 1,
        "user_id": 1,
        "status": CourseStatus.ACTIVE,
        "current_day": 5,
        "total_days": 21,
        "late_count": 0,
        "appeal_count": 0,
        "late_dates": [],
        "created_at": datetime(2026, 1, 1, tzinfo=TASHKENT_TZ),
    }
    defaults.update(overrides)
    return Course(**defaults)


def make_intake_log(**overrides) -> IntakeLog:
    """Create an IntakeLog model object for testing (no DB)."""
    defaults = {
        "id": 1,
        "course_id": 1,
        "day": 1,
        "status": "pending",
        "created_at": datetime(2026, 1, 1, tzinfo=TASHKENT_TZ),
    }
    defaults.update(overrides)
    return IntakeLog(**defaults)


# =============================================================================
# CHECK WINDOW
# =============================================================================


class TestCheckWindow:
    def test_none_intake_time(self, service: VideoService):
        """intake_time=None → always CLOSED."""
        course = make_course(intake_time=None)
        status, hint = service.check_window(course)
        assert status == WindowStatus.CLOSED
        assert hint == ""

    def test_open_normal(self, service: VideoService, frozen_now):
        """intake=14:00, now=14:30 → inside window → OPEN."""
        frozen_now.return_value = datetime(2026, 6, 15, 14, 30, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0))
        status, _ = service.check_window(course)
        assert status == WindowStatus.OPEN

    def test_early_before_window(self, service: VideoService, frozen_now):
        """intake=14:00, now=12:00 → before window → EARLY with hint."""
        frozen_now.return_value = datetime(2026, 6, 15, 12, 0, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0))
        status, hint = service.check_window(course)
        assert status == WindowStatus.EARLY
        assert hint == "13:50"

    def test_closed_after_window(self, service: VideoService, frozen_now):
        """intake=14:00, now=17:00 → past window → CLOSED."""
        frozen_now.return_value = datetime(2026, 6, 15, 17, 0, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0))
        status, _ = service.check_window(course)
        assert status == WindowStatus.CLOSED

    def test_exact_start_boundary(self, service: VideoService, frozen_now):
        """13:50 = scheduled(14:00) - 10min → boundary included (<=)."""
        frozen_now.return_value = datetime(2026, 6, 15, 13, 50, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0))
        status, _ = service.check_window(course)
        assert status == WindowStatus.OPEN

    def test_exact_end_boundary(self, service: VideoService, frozen_now):
        """16:00 = scheduled(14:00) + 120min → boundary included (<=)."""
        frozen_now.return_value = datetime(2026, 6, 15, 16, 0, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0))
        status, _ = service.check_window(course)
        assert status == WindowStatus.OPEN

    def test_one_minute_after_end(self, service: VideoService, frozen_now):
        """16:01 → past end → CLOSED."""
        frozen_now.return_value = datetime(2026, 6, 15, 16, 1, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0))
        status, _ = service.check_window(course)
        assert status == WindowStatus.CLOSED

    def test_midnight_crossing_open(self, service: VideoService, frozen_now):
        """intake=23:30, now=00:15 next day → yesterday's window still open."""
        frozen_now.return_value = datetime(2026, 6, 16, 0, 15, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(23, 30))
        status, _ = service.check_window(course)
        assert status == WindowStatus.OPEN

    def test_midnight_crossing_exact_end(self, service: VideoService, frozen_now):
        """intake=23:30, now=01:30 → exactly yesterday_end → OPEN (<=)."""
        frozen_now.return_value = datetime(2026, 6, 16, 1, 30, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(23, 30))
        status, _ = service.check_window(course)
        assert status == WindowStatus.OPEN

    def test_midnight_crossing_after_end_is_early(
        self, service: VideoService, frozen_now,
    ):
        """intake=23:30, now=01:31 → past yesterday's window.
        But now < today_start(23:20) → EARLY (not CLOSED!), hint=23:20.
        """
        frozen_now.return_value = datetime(2026, 6, 16, 1, 31, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(23, 30))
        status, hint = service.check_window(course)
        assert status == WindowStatus.EARLY
        assert hint == "23:20"


# =============================================================================
# RECORD INTAKE
# =============================================================================


class TestRecordIntake:
    async def test_approved_creates_taken_and_advances_day(
        self,
        service: VideoService,
        mock_course_repo: AsyncMock,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """approved=True → status='taken', verified_by='gemini', day advanced."""
        frozen_now.return_value = datetime(2026, 6, 15, 14, 30, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0), current_day=5)
        mock_intake_log_repo.create.return_value = make_intake_log(id=10)

        await service.record_intake(course, "vid_1", approved=True, confidence=0.95)

        kw = mock_intake_log_repo.create.call_args.kwargs
        assert kw["status"] == "taken"
        assert kw["verified_by"] == "gemini"
        assert kw["day"] == 6
        assert kw["confidence"] == 0.95
        mock_course_repo.update_current_day.assert_called_once_with(1, 6)

    async def test_not_approved_creates_pending_review(
        self,
        service: VideoService,
        mock_course_repo: AsyncMock,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """approved=False → status='pending_review', verified_by=None, no day advance."""
        frozen_now.return_value = datetime(2026, 6, 15, 14, 30, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0), current_day=5)
        mock_intake_log_repo.create.return_value = make_intake_log(id=10)

        await service.record_intake(course, "vid_1", approved=False, confidence=0.5)

        kw = mock_intake_log_repo.create.call_args.kwargs
        assert kw["status"] == "pending_review"
        assert kw["verified_by"] is None
        mock_course_repo.update_current_day.assert_not_called()

    async def test_intake_time_none_scheduled_equals_now(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """intake_time=None → scheduled=now, delay_minutes=None."""
        now = datetime(2026, 6, 15, 14, 30, tzinfo=TASHKENT_TZ)
        frozen_now.return_value = now
        course = make_course(intake_time=None, current_day=5)
        mock_intake_log_repo.create.return_value = make_intake_log()

        await service.record_intake(course, "vid_1", approved=True, confidence=0.9)

        kw = mock_intake_log_repo.create.call_args.kwargs
        assert kw["scheduled_at"] == now
        assert kw["delay_minutes"] is None

    async def test_delay_minutes_when_late(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """30 minutes after scheduled → delay_minutes=30."""
        frozen_now.return_value = datetime(2026, 6, 15, 14, 30, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0), current_day=0)
        mock_intake_log_repo.create.return_value = make_intake_log()

        await service.record_intake(course, "vid_1", approved=True, confidence=0.9)

        kw = mock_intake_log_repo.create.call_args.kwargs
        assert kw["delay_minutes"] == 30

    async def test_delay_minutes_none_when_early(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """5 minutes before scheduled → delta negative → delay_minutes=None."""
        frozen_now.return_value = datetime(2026, 6, 15, 13, 55, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0), current_day=0)
        mock_intake_log_repo.create.return_value = make_intake_log()

        await service.record_intake(course, "vid_1", approved=True, confidence=0.9)

        kw = mock_intake_log_repo.create.call_args.kwargs
        assert kw["delay_minutes"] is None

    async def test_delay_minutes_none_when_exactly_on_time(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """Exactly on time → delta=0 → strictly > 0 is False → None."""
        frozen_now.return_value = datetime(2026, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0), current_day=0)
        mock_intake_log_repo.create.return_value = make_intake_log()

        await service.record_intake(course, "vid_1", approved=True, confidence=0.9)

        kw = mock_intake_log_repo.create.call_args.kwargs
        assert kw["delay_minutes"] is None

    async def test_midnight_crossing_uses_yesterday(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """intake=23:30, now=00:05 → now < today_start → scheduled=yesterday 23:30."""
        frozen_now.return_value = datetime(2026, 6, 16, 0, 5, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(23, 30), current_day=5)
        mock_intake_log_repo.create.return_value = make_intake_log()

        await service.record_intake(course, "vid_1", approved=True, confidence=0.9)

        kw = mock_intake_log_repo.create.call_args.kwargs
        expected_scheduled = datetime(2026, 6, 15, 23, 30, tzinfo=TASHKENT_TZ)
        assert kw["scheduled_at"] == expected_scheduled

    async def test_returns_created_intake_log(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """Returns the IntakeLog object from repo.create."""
        frozen_now.return_value = datetime(2026, 6, 15, 14, 30, tzinfo=TASHKENT_TZ)
        expected_log = make_intake_log(id=42)
        mock_intake_log_repo.create.return_value = expected_log
        course = make_course(intake_time=time(14, 0))

        result = await service.record_intake(
            course, "vid_1", approved=True, confidence=0.9,
        )

        assert result is expected_log


# =============================================================================
# CALCULATE DEADLINE
# =============================================================================


class TestCalculateDeadline:
    def test_tomorrow_intake_minus_2h(self, service: VideoService, frozen_now):
        """intake=14:00, now=June 15 → deadline = June 16 12:00."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0))

        deadline = service.calculate_deadline(course)

        expected = datetime(2026, 6, 16, 12, 0, tzinfo=TASHKENT_TZ)
        assert deadline == expected

    def test_intake_time_none_uses_now(self, service: VideoService, frozen_now):
        """intake_time=None → uses now.time() → tomorrow 10:30 - 2h = 08:30."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 30, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=None)

        deadline = service.calculate_deadline(course)

        expected = datetime(2026, 6, 16, 8, 30, tzinfo=TASHKENT_TZ)
        assert deadline == expected

    def test_date_is_always_tomorrow(self, service: VideoService, frozen_now):
        """Even at 23:00, deadline is tomorrow (not today)."""
        frozen_now.return_value = datetime(2026, 6, 15, 23, 0, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(23, 30))

        deadline = service.calculate_deadline(course)

        assert deadline.date() == datetime(2026, 6, 16).date()
        expected = datetime(2026, 6, 16, 21, 30, tzinfo=TASHKENT_TZ)
        assert deadline == expected


# =============================================================================
# GET MAX STRIKES
# =============================================================================


class TestGetMaxStrikes:
    def test_base_no_appeals(self, service: VideoService):
        """No appeals → base 3 strikes."""
        course = make_course(appeal_count=0)
        assert service.get_max_strikes(course) == 3

    def test_extra_from_appeals(self, service: VideoService):
        """2 accepted appeals → 3 + 2 = 5 strikes."""
        course = make_course(appeal_count=2)
        assert service.get_max_strikes(course) == 5


# =============================================================================
# RECORD LATE
# =============================================================================


class TestRecordLate:
    async def test_increments_and_appends_date(
        self,
        service: VideoService,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """First late: count 0→1, one date added."""
        now = datetime(2026, 6, 15, 14, 35, tzinfo=TASHKENT_TZ)
        frozen_now.return_value = now
        course = make_course(late_count=0, late_dates=[])

        new_count, new_dates = await service.record_late(course)

        assert new_count == 1
        assert len(new_dates) == 1
        assert new_dates[0] == now.isoformat()
        mock_course_repo.record_late.assert_called_once_with(1, 1, new_dates)

    async def test_accumulates_existing_dates(
        self,
        service: VideoService,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """Third late: existing [d1, d2] → [d1, d2, d3]."""
        now = datetime(2026, 6, 15, 14, 35, tzinfo=TASHKENT_TZ)
        frozen_now.return_value = now
        existing = ["2026-06-13T14:35:00+05:00", "2026-06-14T14:40:00+05:00"]
        course = make_course(late_count=2, late_dates=existing)

        new_count, new_dates = await service.record_late(course)

        assert new_count == 3
        assert len(new_dates) == 3
        assert new_dates[:2] == existing
        assert new_dates[2] == now.isoformat()


# =============================================================================
# DELEGATION METHODS — verify correct arguments
# =============================================================================


class TestDelegation:
    async def test_get_today_log_uses_next_day(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
    ):
        """get_today_log uses current_day + 1 (not current_day)."""
        expected_log = make_intake_log(day=6)
        mock_intake_log_repo.get_by_course_and_day.return_value = expected_log
        course = make_course(id=10, current_day=5)

        result = await service.get_today_log(course)

        assert result is expected_log
        mock_intake_log_repo.get_by_course_and_day.assert_called_once_with(10, 6)

    async def test_confirm_marks_taken_by_manager(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        mock_course_repo: AsyncMock,
    ):
        """confirm_intake: status='taken', verified_by='manager', day advanced."""
        mock_intake_log_repo.update_status.return_value = True
        result = await service.confirm_intake(log_id=7, course_id=3, day=10)

        assert result is True
        mock_intake_log_repo.update_status.assert_called_once_with(
            7, "taken", verified_by="manager",
            expected_status="pending_review",
        )
        mock_course_repo.update_current_day.assert_called_once_with(3, 10)

    async def test_confirm_race_condition_returns_false(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        mock_course_repo: AsyncMock,
    ):
        """confirm_intake returns False when already handled."""
        mock_intake_log_repo.update_status.return_value = False
        result = await service.confirm_intake(log_id=7, course_id=3, day=10)

        assert result is False
        mock_course_repo.update_current_day.assert_not_called()

    async def test_reject_marks_rejected_and_refuses(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        mock_course_repo: AsyncMock,
    ):
        """reject_intake: status='rejected' + course refused."""
        mock_intake_log_repo.update_status.return_value = True
        result = await service.reject_intake(log_id=7, course_id=3)

        assert result is True
        mock_intake_log_repo.update_status.assert_called_once_with(
            7, "rejected", expected_status="pending_review",
        )
        mock_course_repo.set_refused.assert_called_once_with(
            3, removal_reason=RemovalReason.MANAGER_REJECT,
        )

    async def test_reject_race_condition_returns_false(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        mock_course_repo: AsyncMock,
    ):
        """reject_intake returns False when already handled."""
        mock_intake_log_repo.update_status.return_value = False
        result = await service.reject_intake(log_id=7, course_id=3)

        assert result is False
        mock_course_repo.set_refused.assert_not_called()

    async def test_complete_course_success(
        self,
        service: VideoService,
        mock_course_repo: AsyncMock,
    ):
        mock_course_repo.complete_course_active.return_value = True
        result = await service.complete_course(course_id=5)
        assert result is True
        mock_course_repo.complete_course_active.assert_called_once_with(5)

    async def test_complete_course_race_condition(
        self,
        service: VideoService,
        mock_course_repo: AsyncMock,
    ):
        """Course already refused by worker → complete_course returns False."""
        mock_course_repo.complete_course_active.return_value = False
        result = await service.complete_course(course_id=5)
        assert result is False
        mock_course_repo.complete_course_active.assert_called_once_with(5)

    async def test_request_reshoot_returns_deadline(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """request_reshoot calculates deadline and returns it."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)
        course = make_course(intake_time=time(14, 0))

        deadline = await service.request_reshoot(log_id=7, course=course)

        expected = datetime(2026, 6, 16, 12, 0, tzinfo=TASHKENT_TZ)
        assert deadline == expected
        mock_intake_log_repo.set_reshoot.assert_called_once_with(7, expected)

    async def test_expire_reshoot_missed_and_refuses(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        mock_course_repo: AsyncMock,
    ):
        """expire_reshoot: status='missed' + course refused."""
        await service.expire_reshoot(log_id=7, course_id=3)

        mock_intake_log_repo.update_status.assert_called_once_with(7, "missed")
        mock_course_repo.set_refused.assert_called_once_with(3, removal_reason="reshoot_expired")

    async def test_accept_reshoot_updates_and_advances(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """accept_reshoot: update_after_reshoot + advance day."""
        now = datetime(2026, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)
        frozen_now.return_value = now

        await service.accept_reshoot(
            log_id=7, course_id=3, day=10,
            video_file_id="new_vid", confidence=0.95, verified_by="gemini",
        )

        mock_intake_log_repo.update_after_reshoot.assert_called_once_with(
            log_id=7,
            status="taken",
            video_file_id="new_vid",
            taken_at=now,
            confidence=0.95,
            verified_by="gemini",
        )
        mock_course_repo.update_current_day.assert_called_once_with(3, 10)

    async def test_reshoot_pending_review(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
        frozen_now,
    ):
        """reshoot_pending_review: status='pending_review', verified_by=None."""
        now = datetime(2026, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)
        frozen_now.return_value = now

        await service.reshoot_pending_review(
            log_id=7, video_file_id="vid_2", confidence=0.4,
        )

        mock_intake_log_repo.update_after_reshoot.assert_called_once_with(
            log_id=7,
            status="pending_review",
            video_file_id="vid_2",
            taken_at=now,
            confidence=0.4,
            verified_by=None,
        )

    async def test_get_pending_reshoot(
        self,
        service: VideoService,
        mock_intake_log_repo: AsyncMock,
    ):
        """get_pending_reshoot uses hardcoded status='reshoot'."""
        expected_log = make_intake_log(status="reshoot")
        mock_intake_log_repo.get_by_course_and_status.return_value = expected_log

        result = await service.get_pending_reshoot(course_id=5)

        assert result is expected_log
        mock_intake_log_repo.get_by_course_and_status.assert_called_once_with(
            5, "reshoot",
        )