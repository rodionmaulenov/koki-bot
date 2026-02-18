"""Tests for CourseRepository — real database, all 23 methods."""
from datetime import date, datetime, time, timedelta

import pytest
from supabase import AsyncClient

from models.enums import CourseStatus
from repositories.course_repository import CourseRepository
from tests.conftest import create_test_course
from utils.time import TASHKENT_TZ


# =============================================================================
# GET BY ID
# =============================================================================


class TestGetById:
    async def test_returns_course_with_all_fields(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        created = await create_test_course(
            supabase, user_id=user_id,
            status="active", invite_code="ABC123",
            intake_time="14:30", start_date="2026-01-15",
            current_day=5, total_days=21, late_count=1,
        )

        course = await course_repository.get_by_id(created.id)

        assert course is not None
        assert course.id == created.id
        assert course.user_id == user_id
        assert course.status == CourseStatus.ACTIVE
        assert course.invite_code == "ABC123"
        assert course.intake_time == time(14, 30)
        assert course.start_date == date(2026, 1, 15)
        assert course.current_day == 5
        assert course.total_days == 21
        assert course.late_count == 1

    async def test_nonexistent_returns_none(
        self, course_repository: CourseRepository,
    ):
        result = await course_repository.get_by_id(999999)
        assert result is None


# =============================================================================
# GET BY INVITE CODE
# =============================================================================


class TestGetByInviteCode:
    async def test_finds_by_code(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        created = await create_test_course(
            supabase, user_id=user_id, invite_code="UNIQUE_CODE_1",
        )

        course = await course_repository.get_by_invite_code("UNIQUE_CODE_1")

        assert course is not None
        assert course.id == created.id
        assert course.invite_code == "UNIQUE_CODE_1"

    async def test_nonexistent_code_returns_none(
        self, course_repository: CourseRepository,
    ):
        result = await course_repository.get_by_invite_code("NONEXISTENT")
        assert result is None


# =============================================================================
# GET ACTIVE BY USER ID
# =============================================================================


class TestGetActiveByUserId:
    """get_active_by_user_id filters by status IN (setup, active, appeal)."""

    async def test_finds_setup(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(supabase, user_id=user_id, status="setup")

        course = await course_repository.get_active_by_user_id(user_id)
        assert course is not None
        assert course.status == CourseStatus.SETUP

    async def test_finds_active(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(supabase, user_id=user_id, status="active")

        course = await course_repository.get_active_by_user_id(user_id)
        assert course is not None
        assert course.status == CourseStatus.ACTIVE

    async def test_finds_appeal(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(supabase, user_id=user_id, status="appeal")

        course = await course_repository.get_active_by_user_id(user_id)
        assert course is not None
        assert course.status == CourseStatus.APPEAL

    async def test_ignores_completed(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(supabase, user_id=user_id, status="completed")

        result = await course_repository.get_active_by_user_id(user_id)
        assert result is None

    async def test_ignores_refused(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(supabase, user_id=user_id, status="refused")

        result = await course_repository.get_active_by_user_id(user_id)
        assert result is None

    async def test_ignores_expired(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(supabase, user_id=user_id, status="expired")

        result = await course_repository.get_active_by_user_id(user_id)
        assert result is None

    async def test_no_courses_returns_none(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        result = await course_repository.get_active_by_user_id(user_id)
        assert result is None


# =============================================================================
# ACTIVATE (atomic: only from setup)
# =============================================================================


class TestActivate:
    async def test_activates_setup_course(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="setup")

        result = await course_repository.activate(
            course.id,
            cycle_day=3,
            intake_time=time(20, 0),
            start_date=date(2026, 2, 12),
        )

        assert result is True
        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.ACTIVE
        assert updated.cycle_day == 3
        assert updated.intake_time == time(20, 0)
        assert updated.start_date == date(2026, 2, 12)
        assert updated.invite_used is True

    async def test_double_activate_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Девушка нажала ссылку дважды — вторая активация не проходит."""
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="setup")

        first = await course_repository.activate(
            course.id, cycle_day=3, intake_time=time(20, 0),
            start_date=date(2026, 2, 12),
        )
        second = await course_repository.activate(
            course.id, cycle_day=2, intake_time=time(10, 0),
            start_date=date(2026, 3, 1),
        )

        assert first is True
        assert second is False
        # Данные от первой активации сохранились
        updated = await course_repository.get_by_id(course.id)
        assert updated.cycle_day == 3
        assert updated.intake_time == time(20, 0)

    async def test_activate_non_setup_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="active")

        result = await course_repository.activate(
            course.id, cycle_day=3, intake_time=time(20, 0),
            start_date=date(2026, 2, 12),
        )
        assert result is False


# =============================================================================
# STATUS TRANSITIONS
# =============================================================================


class TestSetCompleted:
    async def test_sets_completed(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="active")

        await course_repository.set_completed(course.id)

        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.COMPLETED


class TestSetRefused:
    async def test_sets_refused(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="active")

        await course_repository.set_refused(course.id)

        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.REFUSED


class TestSetExpired:
    async def test_sets_expired(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="setup")

        await course_repository.set_expired(course.id)

        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.EXPIRED

    async def test_batch_sets_expired(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        c1 = await create_test_course(
            supabase, user_id=user_id, status="setup", invite_code="BATCH1",
        )
        c2 = await create_test_course(
            supabase, user_id=user_id, status="setup", invite_code="BATCH2",
        )

        await course_repository.set_expired_batch([c1.id, c2.id])

        u1 = await course_repository.get_by_id(c1.id)
        u2 = await course_repository.get_by_id(c2.id)
        assert u1.status == CourseStatus.EXPIRED
        assert u2.status == CourseStatus.EXPIRED

    async def test_batch_empty_list_does_nothing(
        self, course_repository: CourseRepository,
    ):
        """Пустой список — ранний return, без ошибок."""
        await course_repository.set_expired_batch([])


# =============================================================================
# ATOMIC OPERATIONS (race condition protection)
# =============================================================================


class TestRefuseIfActive:
    async def test_refuses_active_course(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="active")

        result = await course_repository.refuse_if_active(course.id)

        assert result is True
        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.REFUSED

    async def test_already_refused_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Воркер пытается снять, но менеджер уже снял — race condition."""
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="refused")

        result = await course_repository.refuse_if_active(course.id)
        assert result is False

    async def test_setup_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="setup")

        result = await course_repository.refuse_if_active(course.id)
        assert result is False


class TestCompleteCourseActive:
    async def test_completes_active_course(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="active")

        result = await course_repository.complete_course_active(course.id)

        assert result is True
        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.COMPLETED

    async def test_already_refused_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Менеджер нажал 'Завершить', но воркер уже снял — race condition."""
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="refused")

        result = await course_repository.complete_course_active(course.id)
        assert result is False

    async def test_double_complete_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Менеджер нажал 'Завершить' дважды."""
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="active")

        first = await course_repository.complete_course_active(course.id)
        second = await course_repository.complete_course_active(course.id)

        assert first is True
        assert second is False


class TestExtendCourse:
    async def test_extends_active_course(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="active",
            total_days=21, extended=False,
        )

        result = await course_repository.extend_course(course.id, new_total=42)

        assert result is True
        updated = await course_repository.get_by_id(course.id)
        assert updated.total_days == 42
        assert updated.extended is True

    async def test_already_extended_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Нельзя продлить дважды."""
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="active",
            total_days=21, extended=False,
        )

        first = await course_repository.extend_course(course.id, new_total=42)
        second = await course_repository.extend_course(course.id, new_total=42)

        assert first is True
        assert second is False

    async def test_not_active_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="refused", extended=False,
        )

        result = await course_repository.extend_course(course.id, new_total=42)
        assert result is False


# =============================================================================
# APPEAL FLOW
# =============================================================================


class TestStartAppeal:
    async def test_starts_appeal_from_refused(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="refused")

        result = await course_repository.start_appeal(course.id)

        assert result is True
        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.APPEAL

    async def test_from_active_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Апелляция возможна только из refused."""
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="active")

        result = await course_repository.start_appeal(course.id)
        assert result is False

    async def test_double_appeal_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="refused")

        first = await course_repository.start_appeal(course.id)
        second = await course_repository.start_appeal(course.id)

        assert first is True
        assert second is False


class TestSaveAppealData:
    async def test_saves_video_and_text(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id, status="appeal")

        await course_repository.save_appeal_data(
            course.id,
            appeal_video="AgACAgIAAxkBAAI",
            appeal_text="Я не успела, была у врача",
        )

        updated = await course_repository.get_by_id(course.id)
        assert updated.appeal_video == "AgACAgIAAxkBAAI"
        assert updated.appeal_text == "Я не успела, была у врача"


class TestAcceptAppeal:
    async def test_accepts_appeal(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="appeal", appeal_count=0,
        )

        result = await course_repository.accept_appeal(course.id, new_appeal_count=1)

        assert result is True
        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.ACTIVE
        assert updated.appeal_count == 1

    async def test_double_accept_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Менеджер нажал 'Принять' дважды."""
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="appeal", appeal_count=0,
        )

        first = await course_repository.accept_appeal(course.id, new_appeal_count=1)
        second = await course_repository.accept_appeal(course.id, new_appeal_count=2)

        assert first is True
        assert second is False
        # appeal_count остался 1 (от первого accept)
        updated = await course_repository.get_by_id(course.id)
        assert updated.appeal_count == 1

    async def test_not_appeal_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="active", appeal_count=0,
        )

        result = await course_repository.accept_appeal(course.id, new_appeal_count=1)
        assert result is False


class TestDeclineAppeal:
    async def test_declines_appeal(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="appeal", appeal_count=0,
        )

        result = await course_repository.decline_appeal(course.id, new_appeal_count=1)

        assert result is True
        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.REFUSED
        assert updated.appeal_count == 1

    async def test_double_decline_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="appeal", appeal_count=0,
        )

        first = await course_repository.decline_appeal(course.id, new_appeal_count=1)
        second = await course_repository.decline_appeal(course.id, new_appeal_count=2)

        assert first is True
        assert second is False


class TestRefuseIfAppeal:
    async def test_auto_refuses_appeal(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Воркер: дедлайн апелляции истёк → авто-отказ."""
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="appeal", appeal_count=0,
        )

        result = await course_repository.refuse_if_appeal(course.id, new_appeal_count=1)

        assert result is True
        updated = await course_repository.get_by_id(course.id)
        assert updated.status == CourseStatus.REFUSED
        assert updated.appeal_count == 1

    async def test_already_handled_returns_false(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Менеджер уже принял апелляцию → воркер не должен отказать."""
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="active", appeal_count=1,
        )

        result = await course_repository.refuse_if_appeal(course.id, new_appeal_count=2)
        assert result is False


# =============================================================================
# COURSE LIFECYCLE
# =============================================================================


class TestRecordLate:
    async def test_updates_late_count_and_dates(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="active",
            late_count=0, late_dates=[],
        )

        late_dates = ["2026-02-11T14:30:00+05:00"]
        await course_repository.record_late(course.id, 1, late_dates)

        updated = await course_repository.get_by_id(course.id)
        assert updated.late_count == 1
        assert updated.late_dates == late_dates

    async def test_accumulates_late_dates(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Каждый страйк добавляет дату, не перезаписывает."""
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="active",
            late_count=1, late_dates=["2026-02-10T14:30:00+05:00"],
        )

        new_dates = ["2026-02-10T14:30:00+05:00", "2026-02-11T14:30:00+05:00"]
        await course_repository.record_late(course.id, 2, new_dates)

        updated = await course_repository.get_by_id(course.id)
        assert updated.late_count == 2
        assert len(updated.late_dates) == 2


class TestUpdateCurrentDay:
    async def test_updates_day(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="active", current_day=5,
        )

        await course_repository.update_current_day(course.id, 6)

        updated = await course_repository.get_by_id(course.id)
        assert updated.current_day == 6


class TestSetRegistrationMessageId:
    async def test_sets_message_id(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(supabase, user_id=user_id)

        await course_repository.set_registration_message_id(course.id, 12345)

        updated = await course_repository.get_by_id(course.id)
        assert updated.registration_message_id == 12345


class TestReissue:
    async def test_resets_course_to_setup(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        course = await create_test_course(
            supabase, user_id=user_id, status="expired",
            invite_code="OLD_CODE", invite_used=True,
            current_day=10, intake_time="14:00", start_date="2026-01-01",
        )

        result = await course_repository.reissue(course.id, "NEW_CODE_123")

        assert result.status == CourseStatus.SETUP
        assert result.invite_code == "NEW_CODE_123"
        assert result.invite_used is False
        assert result.current_day == 0
        assert result.cycle_day is None
        assert result.intake_time is None
        assert result.start_date is None

    async def test_nonexistent_raises_runtime_error(
        self, course_repository: CourseRepository,
    ):
        with pytest.raises(RuntimeError, match="Course not found"):
            await course_repository.reissue(999999, "CODE")


# =============================================================================
# WORKER QUERIES
# =============================================================================


class TestGetActiveInIntakeWindow:
    """Фильтрация: status=active, start_date <= today, intake_time in range."""

    async def test_finds_course_in_window(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(
            supabase, user_id=user_id, status="active",
            intake_time="14:00", start_date="2026-01-01",
        )

        courses = await course_repository.get_active_in_intake_window(
            "2026-02-11", "13:55", "14:05",
        )
        assert len(courses) == 1
        assert courses[0].intake_time == time(14, 0)

    async def test_excludes_outside_window(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(
            supabase, user_id=user_id, status="active",
            intake_time="14:00", start_date="2026-01-01",
        )

        courses = await course_repository.get_active_in_intake_window(
            "2026-02-11", "15:00", "15:10",
        )
        assert len(courses) == 0

    async def test_excludes_non_active(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Курс refused — воркер не должен его видеть."""
        _, user_id = make_user
        await create_test_course(
            supabase, user_id=user_id, status="refused",
            intake_time="14:00", start_date="2026-01-01",
        )

        courses = await course_repository.get_active_in_intake_window(
            "2026-02-11", "13:55", "14:05",
        )
        assert len(courses) == 0

    async def test_excludes_future_start_date(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Курс ещё не начался (start_date > today) — воркер не видит."""
        _, user_id = make_user
        await create_test_course(
            supabase, user_id=user_id, status="active",
            intake_time="14:00", start_date="2099-12-31",
        )

        courses = await course_repository.get_active_in_intake_window(
            "2026-02-11", "13:55", "14:05",
        )
        assert len(courses) == 0

    async def test_boundary_exact_time_included(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """intake_time ровно на границе диапазона — включается (>=, <=)."""
        _, user_id = make_user
        await create_test_course(
            supabase, user_id=user_id, status="active",
            intake_time="14:00", start_date="2026-01-01",
        )

        # Ровно на левой границе
        courses = await course_repository.get_active_in_intake_window(
            "2026-02-11", "14:00", "14:10",
        )
        assert len(courses) == 1

        # Ровно на правой границе
        courses = await course_repository.get_active_in_intake_window(
            "2026-02-11", "13:50", "14:00",
        )
        assert len(courses) == 1


class TestGetAppealCourses:
    async def test_returns_appeal_courses(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(supabase, user_id=user_id, status="appeal")

        courses = await course_repository.get_appeal_courses()
        assert len(courses) == 1
        assert courses[0].status == CourseStatus.APPEAL

    async def test_excludes_other_statuses(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(
            supabase, user_id=user_id, status="active", invite_code="A1",
        )
        await create_test_course(
            supabase, user_id=user_id, status="refused", invite_code="A2",
        )

        courses = await course_repository.get_appeal_courses()
        assert len(courses) == 0

    async def test_empty_returns_empty_list(
        self, course_repository: CourseRepository,
    ):
        courses = await course_repository.get_appeal_courses()
        assert courses == []


class TestGetReissuableByUserIds:
    async def test_returns_setup_and_expired(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        _, user_id = make_user
        await create_test_course(
            supabase, user_id=user_id, status="setup", invite_code="R1",
        )
        await create_test_course(
            supabase, user_id=user_id, status="expired", invite_code="R2",
        )
        # active — не должен попасть
        await create_test_course(
            supabase, user_id=user_id, status="active", invite_code="R3",
        )

        cutoff = datetime.now(tz=TASHKENT_TZ) - timedelta(days=7)
        courses = await course_repository.get_reissuable_by_user_ids(
            [user_id], cutoff=cutoff,
        )

        statuses = {c.status for c in courses}
        assert CourseStatus.ACTIVE not in statuses
        assert len(courses) == 2

    async def test_cutoff_filters_old_courses(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Курсы старше cutoff не возвращаются."""
        _, user_id = make_user
        await create_test_course(
            supabase, user_id=user_id, status="setup",
        )

        # cutoff = далеко в будущем → все курсы "старые"
        future_cutoff = datetime.now(tz=TASHKENT_TZ) + timedelta(days=30)
        courses = await course_repository.get_reissuable_by_user_ids(
            [user_id], cutoff=future_cutoff,
        )
        assert len(courses) == 0

    async def test_empty_user_ids(
        self, supabase: AsyncClient, course_repository: CourseRepository,
    ):
        cutoff = datetime.now(tz=TASHKENT_TZ) - timedelta(days=7)
        courses = await course_repository.get_reissuable_by_user_ids(
            [], cutoff=cutoff,
        )
        assert courses == []

    async def test_ordered_by_created_at_desc(
        self, supabase: AsyncClient, make_user, course_repository: CourseRepository,
    ):
        """Самый новый курс первым."""
        _, user_id = make_user
        c1 = await create_test_course(
            supabase, user_id=user_id, status="setup", invite_code="OLD1",
        )
        c2 = await create_test_course(
            supabase, user_id=user_id, status="setup", invite_code="NEW2",
        )

        cutoff = datetime.now(tz=TASHKENT_TZ) - timedelta(days=7)
        courses = await course_repository.get_reissuable_by_user_ids(
            [user_id], cutoff=cutoff,
        )

        assert len(courses) >= 2
        assert courses[0].id == c2.id  # новый первым
        assert courses[1].id == c1.id