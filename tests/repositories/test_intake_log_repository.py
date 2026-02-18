"""Tests for IntakeLogRepository — real database, all 11 methods."""
from datetime import datetime, timedelta

from supabase import AsyncClient

from models.course import Course
from repositories.intake_log_repository import IntakeLogRepository
from tests.conftest import create_test_course, create_test_intake_log
from utils.time import TASHKENT_TZ

# Deterministic timestamps for repeatable tests
_BASE = datetime(2026, 6, 15, 14, 0, 0, tzinfo=TASHKENT_TZ)
_BASE_PLUS_5 = _BASE + timedelta(minutes=5)
_BASE_PLUS_15 = _BASE + timedelta(minutes=15)


# =============================================================================
# CREATE
# =============================================================================


class TestCreate:
    async def test_creates_with_required_fields_only(
        self, make_course: Course, intake_log_repository: IntakeLogRepository,
    ):
        log = await intake_log_repository.create(
            course_id=make_course.id,
            day=1,
            scheduled_at=_BASE,
            taken_at=_BASE,
            status="taken",
            video_file_id="video_abc",
        )

        assert log.id is not None
        assert log.course_id == make_course.id
        assert log.day == 1
        assert log.status == "taken"
        assert log.video_file_id == "video_abc"
        assert log.delay_minutes is None
        assert log.verified_by is None
        assert log.confidence is None
        assert log.review_started_at is None

    async def test_creates_with_all_optional_fields(
        self, make_course: Course, intake_log_repository: IntakeLogRepository,
    ):
        log = await intake_log_repository.create(
            course_id=make_course.id,
            day=3,
            scheduled_at=_BASE,
            taken_at=_BASE_PLUS_15,
            status="taken",
            video_file_id="video_xyz",
            delay_minutes=15,
            verified_by="gemini",
            confidence=0.95,
        )

        assert log.delay_minutes == 15
        assert log.verified_by == "gemini"
        assert log.confidence == 0.95

    async def test_pending_review_auto_sets_review_started_at(
        self, make_course: Course, intake_log_repository: IntakeLogRepository,
    ):
        """status='pending_review' → review_started_at автоматически = taken_at.
        Это значение используется воркером review_deadline для отсчёта дедлайна.
        """
        log = await intake_log_repository.create(
            course_id=make_course.id,
            day=1,
            scheduled_at=_BASE,
            taken_at=_BASE_PLUS_5,
            status="pending_review",
            video_file_id="video_pending",
        )

        assert log.review_started_at is not None

    async def test_taken_does_not_set_review_started_at(
        self, make_course: Course, intake_log_repository: IntakeLogRepository,
    ):
        """status='taken' → review_started_at остаётся None (только pending_review ставит)."""
        log = await intake_log_repository.create(
            course_id=make_course.id,
            day=1,
            scheduled_at=_BASE,
            taken_at=_BASE,
            status="taken",
            video_file_id="video_ok",
        )

        assert log.review_started_at is None

    async def test_zero_delay_minutes_is_saved(
        self, make_course: Course, intake_log_repository: IntakeLogRepository,
    ):
        """delay_minutes=0 — 'вовремя'. Не должен трактоваться как None."""
        log = await intake_log_repository.create(
            course_id=make_course.id,
            day=1,
            scheduled_at=_BASE,
            taken_at=_BASE,
            status="taken",
            video_file_id="video_ontime",
            delay_minutes=0,
        )

        assert log.delay_minutes == 0


# =============================================================================
# GET BY ID
# =============================================================================


class TestGetById:
    async def test_returns_all_fields(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        created = await create_test_intake_log(
            supabase, course_id=make_course.id, day=5,
            scheduled_at=_BASE.isoformat(),
            taken_at=_BASE_PLUS_5.isoformat(),
            status="taken",
            video_file_id="vid_123",
            delay_minutes=5,
            verified_by="gemini",
            confidence=0.9,
        )

        log = await intake_log_repository.get_by_id(created.id)

        assert log is not None
        assert log.id == created.id
        assert log.course_id == make_course.id
        assert log.day == 5
        assert log.status == "taken"
        assert log.video_file_id == "vid_123"
        assert log.delay_minutes == 5
        assert log.verified_by == "gemini"
        assert log.confidence == 0.9
        assert log.created_at is not None

    async def test_nonexistent_returns_none(
        self, intake_log_repository: IntakeLogRepository,
    ):
        result = await intake_log_repository.get_by_id(999999)
        assert result is None


# =============================================================================
# GET BY COURSE AND DAY
# =============================================================================


class TestGetByCourseAndDay:
    async def test_finds_existing(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        created = await create_test_intake_log(
            supabase, course_id=make_course.id, day=5,
        )

        log = await intake_log_repository.get_by_course_and_day(make_course.id, 5)

        assert log is not None
        assert log.id == created.id
        assert log.day == 5

    async def test_returns_none_when_no_log(
        self, make_course: Course, intake_log_repository: IntakeLogRepository,
    ):
        result = await intake_log_repository.get_by_course_and_day(make_course.id, 1)
        assert result is None

    async def test_different_day_returns_none(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        await create_test_intake_log(
            supabase, course_id=make_course.id, day=5,
        )

        result = await intake_log_repository.get_by_course_and_day(make_course.id, 6)
        assert result is None

    async def test_different_course_returns_none(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """Лог у курса A, ищем у курса B — изоляция данных."""
        await create_test_intake_log(
            supabase, course_id=make_course.id, day=5,
        )
        course_b = await create_test_course(
            supabase, user_id=make_course.user_id,
            status="active", invite_code="COURSE_B",
        )

        result = await intake_log_repository.get_by_course_and_day(course_b.id, 5)
        assert result is None


# =============================================================================
# UPDATE STATUS
# =============================================================================


class TestUpdateStatus:
    async def test_updates_status(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        log = await create_test_intake_log(
            supabase, course_id=make_course.id, status="pending_review",
        )

        await intake_log_repository.update_status(log.id, "taken")

        updated = await intake_log_repository.get_by_id(log.id)
        assert updated.status == "taken"

    async def test_sets_verified_by(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        log = await create_test_intake_log(
            supabase, course_id=make_course.id, status="pending_review",
        )

        await intake_log_repository.update_status(
            log.id, "taken", verified_by="manager",
        )

        updated = await intake_log_repository.get_by_id(log.id)
        assert updated.verified_by == "manager"

    async def test_without_verified_by_keeps_existing(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """Обновление без verified_by не затирает существующее значение."""
        log = await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="pending_review", verified_by="gemini",
        )

        await intake_log_repository.update_status(log.id, "taken")

        updated = await intake_log_repository.get_by_id(log.id)
        assert updated.status == "taken"
        assert updated.verified_by == "gemini"


# =============================================================================
# SET PRIVATE MESSAGE ID
# =============================================================================


class TestSetPrivateMessageId:
    async def test_sets_message_id(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        log = await create_test_intake_log(
            supabase, course_id=make_course.id,
        )

        await intake_log_repository.set_private_message_id(log.id, 54321)

        updated = await intake_log_repository.get_by_id(log.id)
        assert updated.private_message_id == 54321


# =============================================================================
# SET RESHOOT
# =============================================================================


class TestSetReshoot:
    async def test_sets_status_and_deadline(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        log = await create_test_intake_log(
            supabase, course_id=make_course.id, status="pending_review",
        )
        deadline = _BASE + timedelta(hours=2)

        await intake_log_repository.set_reshoot(log.id, deadline)

        updated = await intake_log_repository.get_by_id(log.id)
        assert updated.status == "reshoot"
        assert updated.reshoot_deadline is not None


# =============================================================================
# GET BY COURSE AND STATUS
# =============================================================================


class TestGetByCourseAndStatus:
    async def test_finds_by_status(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        await create_test_intake_log(
            supabase, course_id=make_course.id, day=1, status="pending_review",
        )

        log = await intake_log_repository.get_by_course_and_status(
            make_course.id, "pending_review",
        )

        assert log is not None
        assert log.status == "pending_review"

    async def test_returns_latest_day_when_multiple(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """Два лога pending_review: день 3 и день 7 → возвращает день 7 (ORDER BY day DESC)."""
        await create_test_intake_log(
            supabase, course_id=make_course.id,
            day=3, status="pending_review", video_file_id="vid_day3",
        )
        await create_test_intake_log(
            supabase, course_id=make_course.id,
            day=7, status="pending_review", video_file_id="vid_day7",
        )

        log = await intake_log_repository.get_by_course_and_status(
            make_course.id, "pending_review",
        )

        assert log is not None
        assert log.day == 7
        assert log.video_file_id == "vid_day7"

    async def test_no_match_returns_none(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        await create_test_intake_log(
            supabase, course_id=make_course.id, status="taken",
        )

        result = await intake_log_repository.get_by_course_and_status(
            make_course.id, "pending_review",
        )
        assert result is None


# =============================================================================
# HAS LOG TODAY
# =============================================================================


class TestHasLogToday:
    async def test_true_when_exists(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        await create_test_intake_log(
            supabase, course_id=make_course.id, day=5,
        )

        result = await intake_log_repository.has_log_today(make_course.id, 5)
        assert result is True

    async def test_false_when_missing(
        self, make_course: Course, intake_log_repository: IntakeLogRepository,
    ):
        result = await intake_log_repository.has_log_today(make_course.id, 1)
        assert result is False

    async def test_different_course_not_counted(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """Лог у курса B не считается за курс A."""
        course_b = await create_test_course(
            supabase, user_id=make_course.user_id,
            status="active", invite_code="COURSE_B2",
        )
        await create_test_intake_log(
            supabase, course_id=course_b.id, day=5,
        )

        result = await intake_log_repository.has_log_today(make_course.id, 5)
        assert result is False


# =============================================================================
# GET PENDING REVIEWS WITH START (worker: review_deadline)
# =============================================================================


class TestGetPendingReviewsWithStart:
    async def test_returns_pending_with_start(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="pending_review",
            review_started_at=_BASE.isoformat(),
        )

        logs = await intake_log_repository.get_pending_reviews_with_start()

        assert len(logs) == 1
        assert logs[0].status == "pending_review"
        assert logs[0].review_started_at is not None

    async def test_excludes_taken(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="taken",
            review_started_at=_BASE.isoformat(),
        )

        logs = await intake_log_repository.get_pending_reviews_with_start()
        assert len(logs) == 0

    async def test_excludes_pending_without_start(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """pending_review с review_started_at=NULL — не попадает в выборку."""
        await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="pending_review",
            # review_started_at НЕ передаём — останется NULL
        )

        logs = await intake_log_repository.get_pending_reviews_with_start()
        assert len(logs) == 0


# =============================================================================
# GET EXPIRED RESHOOTS (worker: reshoot_deadline)
# =============================================================================


class TestGetExpiredReshoots:
    async def test_returns_expired(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        past = _BASE - timedelta(hours=1)
        await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="reshoot",
            reshoot_deadline=past.isoformat(),
        )

        logs = await intake_log_repository.get_expired_reshoots(_BASE.isoformat())

        assert len(logs) == 1
        assert logs[0].status == "reshoot"

    async def test_excludes_future_deadline(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        future = _BASE + timedelta(hours=1)
        await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="reshoot",
            reshoot_deadline=future.isoformat(),
        )

        logs = await intake_log_repository.get_expired_reshoots(_BASE.isoformat())
        assert len(logs) == 0

    async def test_excludes_non_reshoot_status(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """status=taken с прошедшим дедлайном — не попадает."""
        past = _BASE - timedelta(hours=1)
        await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="taken",
            reshoot_deadline=past.isoformat(),
        )

        logs = await intake_log_repository.get_expired_reshoots(_BASE.isoformat())
        assert len(logs) == 0

    async def test_exact_deadline_not_returned(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """reshoot_deadline == now → НЕ возвращается (lt, не lte).
        Если кто-то поменяет lt на lte — тест упадёт.
        """
        exact = _BASE
        await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="reshoot",
            reshoot_deadline=exact.isoformat(),
        )

        logs = await intake_log_repository.get_expired_reshoots(exact.isoformat())
        assert len(logs) == 0


# =============================================================================
# UPDATE AFTER RESHOOT
# =============================================================================


class TestUpdateAfterReshoot:
    async def test_updates_all_fields(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        log = await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="reshoot", video_file_id="old_video",
        )
        new_taken = _BASE + timedelta(hours=1)

        await intake_log_repository.update_after_reshoot(
            log_id=log.id,
            status="taken",
            video_file_id="new_video_reshoot",
            taken_at=new_taken,
            confidence=0.88,
            verified_by="manager",
        )

        updated = await intake_log_repository.get_by_id(log.id)
        assert updated.status == "taken"
        assert updated.video_file_id == "new_video_reshoot"
        assert updated.confidence == 0.88
        assert updated.verified_by == "manager"

    async def test_pending_review_sets_review_started_at(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """Решут → AI не уверен → review_started_at обновляется для нового дедлайна."""
        log = await create_test_intake_log(
            supabase, course_id=make_course.id, status="reshoot",
        )
        new_taken = _BASE + timedelta(hours=1)

        await intake_log_repository.update_after_reshoot(
            log_id=log.id,
            status="pending_review",
            video_file_id="reshoot_vid",
            taken_at=new_taken,
            confidence=0.4,
        )

        updated = await intake_log_repository.get_by_id(log.id)
        assert updated.review_started_at is not None

    async def test_taken_does_not_set_review_started_at(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """Решут → AI уверен (status=taken) → review_started_at НЕ обновляется."""
        log = await create_test_intake_log(
            supabase, course_id=make_course.id, status="reshoot",
        )

        await intake_log_repository.update_after_reshoot(
            log_id=log.id,
            status="taken",
            video_file_id="reshoot_ok",
            taken_at=_BASE,
            confidence=0.95,
        )

        updated = await intake_log_repository.get_by_id(log.id)
        assert updated.review_started_at is None

    async def test_without_verified_by_keeps_existing(
        self, supabase: AsyncClient, make_course: Course,
        intake_log_repository: IntakeLogRepository,
    ):
        """Обновление без verified_by не затирает существующее."""
        log = await create_test_intake_log(
            supabase, course_id=make_course.id,
            status="reshoot", verified_by="gemini",
        )

        await intake_log_repository.update_after_reshoot(
            log_id=log.id,
            status="taken",
            video_file_id="reshoot_vid2",
            taken_at=_BASE,
            confidence=0.88,
            # verified_by не передаём
        )

        updated = await intake_log_repository.get_by_id(log.id)
        assert updated.verified_by == "gemini"