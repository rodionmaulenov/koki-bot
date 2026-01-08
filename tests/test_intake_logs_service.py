"""Тесты для IntakeLogsService."""

import pytest


class TestIntakeLogsServiceCreate:
    """Тесты создания записей."""

    @pytest.mark.asyncio
    async def test_creates_log(self, intake_logs_service, test_active_course):
        """Создаёт запись о приёме."""
        log = await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=1,
            status="taken",
            video_file_id="test_video_123",
        )

        assert log["course_id"] == test_active_course["id"]
        assert log["day"] == 1
        assert log["status"] == "taken"
        assert log["video_file_id"] == "test_video_123"

    @pytest.mark.asyncio
    async def test_creates_log_with_verification(self, intake_logs_service, test_active_course):
        """Создаёт запись с данными верификации."""
        log = await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=2,
            status="taken",
            video_file_id="test_video_456",
            verified_by="gemini",
            confidence=85.5,
        )

        assert log["verified_by"] == "gemini"
        assert log["confidence"] == 85.5

    @pytest.mark.asyncio
    async def test_creates_pending_review_log(self, intake_logs_service, test_active_course):
        """Создаёт запись со статусом pending_review."""
        log = await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=3,
            status="pending_review",
            video_file_id="test_video_789",
            confidence=45.0,
        )

        assert log["status"] == "pending_review"
        assert log["confidence"] == 45.0


class TestIntakeLogsServiceGetByCourseAndDay:
    """Тесты получения записей."""

    @pytest.mark.asyncio
    async def test_finds_existing_log(self, intake_logs_service, test_active_course):
        """Находит существующую запись."""
        # Создаём запись
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=5,
            status="taken",
            video_file_id="find_test_video",
        )

        # Ищем
        log = await intake_logs_service.get_by_course_and_day(
            course_id=test_active_course["id"],
            day=5,
        )

        assert log is not None
        assert log["video_file_id"] == "find_test_video"

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, intake_logs_service, test_active_course):
        """Возвращает None если запись не найдена."""
        log = await intake_logs_service.get_by_course_and_day(
            course_id=test_active_course["id"],
            day=999,
        )

        assert log is None

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_course(self, intake_logs_service, test_active_course):
        """Возвращает None для несуществующего курса."""
        log = await intake_logs_service.get_by_course_and_day(
            course_id=99999,
            day=1,
        )

        assert log is None


class TestIntakeLogsServiceUpdateStatus:
    """Тесты обновления статуса."""

    @pytest.mark.asyncio
    async def test_updates_status(self, intake_logs_service, test_active_course, supabase):
        """Обновляет статус записи."""
        # Создаём запись
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=10,
            status="pending_review",
            video_file_id="update_test_video",
        )

        # Обновляем статус
        await intake_logs_service.update_status(
            course_id=test_active_course["id"],
            day=10,
            status="taken",
        )

        # Проверяем
        log = await intake_logs_service.get_by_course_and_day(
            course_id=test_active_course["id"],
            day=10,
        )

        assert log["status"] == "taken"

    @pytest.mark.asyncio
    async def test_updates_status_with_verified_by(self, intake_logs_service, test_active_course):
        """Обновляет статус и verified_by."""
        # Создаём запись
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=11,
            status="pending_review",
            video_file_id="verify_test_video",
        )

        # Обновляем с verified_by
        await intake_logs_service.update_status(
            course_id=test_active_course["id"],
            day=11,
            status="taken",
            verified_by="manager",
        )

        # Проверяем
        log = await intake_logs_service.get_by_course_and_day(
            course_id=test_active_course["id"],
            day=11,
        )

        assert log["status"] == "taken"
        assert log["verified_by"] == "manager"

    @pytest.mark.asyncio
    async def test_updates_to_rejected(self, intake_logs_service, test_active_course):
        """Обновляет статус на rejected."""
        # Создаём запись
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=12,
            status="pending_review",
            video_file_id="reject_test_video",
        )

        # Отклоняем
        await intake_logs_service.update_status(
            course_id=test_active_course["id"],
            day=12,
            status="rejected",
            verified_by="manager",
        )

        # Проверяем
        log = await intake_logs_service.get_by_course_and_day(
            course_id=test_active_course["id"],
            day=12,
        )

        assert log["status"] == "rejected"
        assert log["verified_by"] == "manager"