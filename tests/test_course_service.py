"""Тесты для CourseService."""
import pytest
import secrets


class TestCourseServiceCreate:
    """Тесты для create()."""

    @pytest.mark.asyncio
    async def test_creates_course(self, course_service, test_user):
        """Создаёт курс."""
        invite_code = secrets.token_urlsafe(8)

        course = await course_service.create(
            user_id=test_user["id"],
            invite_code=invite_code,
        )

        assert course is not None
        assert course["user_id"] == test_user["id"]
        assert course["invite_code"] == invite_code
        assert course["status"] == "setup"

    @pytest.mark.asyncio
    async def test_creates_course_with_defaults(self, course_service, test_user):
        """Создаёт курс с дефолтными значениями."""
        invite_code = secrets.token_urlsafe(8)

        course = await course_service.create(
            user_id=test_user["id"],
            invite_code=invite_code,
        )

        assert course["invite_used"] is False
        assert course["current_day"] == 0
        assert course["late_count"] == 0


class TestCourseServiceGetByInviteCode:
    """Тесты для get_by_invite_code()."""

    @pytest.mark.asyncio
    async def test_finds_course(self, course_service, test_course):
        """Находит курс по invite_code."""
        course = await course_service.get_by_invite_code(test_course["invite_code"])

        assert course is not None
        assert course["id"] == test_course["id"]

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, course_service):
        """Возвращает None для несуществующего кода."""
        course = await course_service.get_by_invite_code("nonexistent_code")

        assert course is None


class TestCourseServiceMarkInviteUsed:
    """Тесты для mark_invite_used()."""

    @pytest.mark.asyncio
    async def test_marks_invite_used(self, course_service, test_course):
        """Отмечает ссылку как использованную."""
        await course_service.mark_invite_used(test_course["id"])

        course = await course_service.get_by_invite_code(test_course["invite_code"])
        assert course["invite_used"] is True


class TestCourseServiceGetActiveByUserId:
    """Тесты для get_active_by_user_id()."""

    @pytest.mark.asyncio
    async def test_finds_setup_course(self, course_service, test_course, test_user):
        """Находит курс в статусе setup."""
        course = await course_service.get_active_by_user_id(test_user["id"])

        assert course is not None
        assert course["id"] == test_course["id"]

    @pytest.mark.asyncio
    async def test_finds_active_course(self, course_service, test_active_course, test_user_with_telegram):
        """Находит курс в статусе active."""
        course = await course_service.get_active_by_user_id(test_user_with_telegram["id"])

        assert course is not None
        assert course["status"] == "active"

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, course_service):
        """Возвращает None для несуществующего user_id."""
        course = await course_service.get_active_by_user_id(999999999)

        assert course is None


class TestCourseServiceUpdate:
    """Тесты для update()."""

    @pytest.mark.asyncio
    async def test_updates_single_field(self, course_service, test_course):
        """Обновляет одно поле."""
        await course_service.update(
            course_id=test_course["id"],
            cycle_day=3,
        )

        course = await course_service.get_by_invite_code(test_course["invite_code"])
        assert course["cycle_day"] == 3

    @pytest.mark.asyncio
    async def test_updates_multiple_fields(self, course_service, test_course):
        """Обновляет несколько полей."""
        await course_service.update(
            course_id=test_course["id"],
            status="active",
            intake_time="14:00",
            current_day=1,
        )

        course = await course_service.get_by_invite_code(test_course["invite_code"])
        assert course["status"] == "active"
        assert course["intake_time"].startswith("14:00")  # PostgreSQL добавляет секунды
        assert course["current_day"] == 1