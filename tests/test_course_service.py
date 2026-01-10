"""Тесты для CourseService."""
import pytest
from unittest.mock import MagicMock

from tests.conftest import create_supabase_chain


class TestCourseService:
    """Тесты для CourseService."""

    @pytest.mark.asyncio
    async def test_get_by_invite_code_found(self, mock_supabase):
        """Находит курс по invite_code."""
        from app.services.courses import CourseService

        chain = create_supabase_chain([{"id": 1, "invite_code": "abc123"}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        course = await service.get_by_invite_code("abc123")

        assert course is not None
        assert course["invite_code"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_by_invite_code_not_found(self, mock_supabase):
        """Возвращает None если не найден."""
        from app.services.courses import CourseService

        chain = create_supabase_chain([])
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        course = await service.get_by_invite_code("nonexistent")

        assert course is None

    @pytest.mark.asyncio
    async def test_mark_invite_used(self, mock_supabase):
        """Отмечает инвайт использованным."""
        from app.services.courses import CourseService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        await service.mark_invite_used(1)

        chain.update.assert_called_once_with({"invite_used": True})

    @pytest.mark.asyncio
    async def test_get_active_by_user_id_found(self, mock_supabase):
        """Находит активный курс."""
        from app.services.courses import CourseService

        chain = create_supabase_chain([{"id": 1, "user_id": 1, "status": "active"}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        course = await service.get_active_by_user_id(1)

        assert course is not None
        assert course["status"] == "active"

    @pytest.mark.asyncio
    async def test_update(self, mock_supabase):
        """Обновляет курс."""
        from app.services.courses import CourseService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        await service.update(course_id=1, current_day=5, late_count=2)

        chain.update.assert_called_once_with({"current_day": 5, "late_count": 2})

    @pytest.mark.asyncio
    async def test_set_refused(self, mock_supabase):
        """Устанавливает статус refused."""
        from app.services.courses import CourseService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        await service.set_refused(1)

        chain.update.assert_called_once_with({"status": "refused"})

    @pytest.mark.asyncio
    async def test_get_active_started(self, mock_supabase):
        """Возвращает активные начавшиеся курсы."""
        from app.services.courses import CourseService

        courses = [
            {"id": 1, "status": "active"},
            {"id": 2, "status": "active"},
        ]
        chain = create_supabase_chain(courses)
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        result = await service.get_active_started("2026-01-10")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, mock_supabase):
        """Находит курс по id."""
        from app.services.courses import CourseService

        chain = create_supabase_chain([{"id": 5, "status": "active"}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        course = await service.get_by_id(5)

        assert course is not None
        assert course["id"] == 5

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mock_supabase):
        """Возвращает None если курс не найден."""
        from app.services.courses import CourseService

        chain = create_supabase_chain([])
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        course = await service.get_by_id(999)

        assert course is None

    @pytest.mark.asyncio
    async def test_set_expired(self, mock_supabase):
        """Устанавливает статус expired."""
        from app.services.courses import CourseService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        await service.set_expired(1)

        chain.update.assert_called_once_with({"status": "expired"})

    @pytest.mark.asyncio
    async def test_create_new_course(self, mock_supabase):
        """Создаёт новый курс."""
        from app.services.courses import CourseService

        # Нет существующего курса
        chain_select = create_supabase_chain([])
        chain_insert = create_supabase_chain([{"id": 1, "user_id": 10, "invite_code": "abc", "status": "setup"}])

        call_count = [0]
        def table_side_effect(name):
            call_count[0] += 1
            if call_count[0] == 1:
                return chain_select
            return chain_insert

        mock_supabase.table = MagicMock(side_effect=table_side_effect)

        service = CourseService(mock_supabase)
        course = await service.create(user_id=10, invite_code="abc")

        assert course["id"] == 1
        assert course["status"] == "setup"

    @pytest.mark.asyncio
    async def test_create_returns_existing_setup(self, mock_supabase):
        """Возвращает существующий setup курс с неиспользованной ссылкой."""
        from app.services.courses import CourseService

        existing = {"id": 5, "user_id": 10, "status": "setup", "invite_used": False}
        chain = create_supabase_chain([existing])
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)
        course = await service.create(user_id=10, invite_code="abc")

        assert course["id"] == 5

    @pytest.mark.asyncio
    async def test_create_raises_if_active_exists(self, mock_supabase):
        """Бросает ошибку если есть активный курс."""
        from app.services.courses import CourseService

        existing = {"id": 5, "user_id": 10, "status": "active", "invite_used": True}
        chain = create_supabase_chain([existing])
        mock_supabase.table = MagicMock(return_value=chain)

        service = CourseService(mock_supabase)

        with pytest.raises(ValueError, match="already has active course"):
            await service.create(user_id=10, invite_code="abc")