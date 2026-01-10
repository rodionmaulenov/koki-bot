"""Тесты для IntakeLogsService."""
import pytest
from unittest.mock import MagicMock

from tests.conftest import create_supabase_chain


class TestIntakeLogsService:
    """Тесты для IntakeLogsService."""

    @pytest.mark.asyncio
    async def test_create(self, mock_supabase):
        """Создаёт запись приёма."""
        from app.services.intake_logs import IntakeLogsService

        chain = create_supabase_chain([{"id": 1, "course_id": 1, "day": 5, "status": "taken"}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = IntakeLogsService(mock_supabase)
        log = await service.create(
            course_id=1,
            day=5,
            status="taken",
            video_file_id="test_file_id",
        )

        assert log["course_id"] == 1
        assert log["status"] == "taken"

    @pytest.mark.asyncio
    async def test_get_by_course_and_day_found(self, mock_supabase):
        """Находит запись по курсу и дню."""
        from app.services.intake_logs import IntakeLogsService

        chain = create_supabase_chain([{"id": 1, "course_id": 1, "day": 5}])
        mock_supabase.table = MagicMock(return_value=chain)

        service = IntakeLogsService(mock_supabase)
        log = await service.get_by_course_and_day(1, 5)

        assert log is not None
        assert log["day"] == 5

    @pytest.mark.asyncio
    async def test_get_by_course_and_day_not_found(self, mock_supabase):
        """Возвращает None если не найдена."""
        from app.services.intake_logs import IntakeLogsService

        chain = create_supabase_chain([])
        mock_supabase.table = MagicMock(return_value=chain)

        service = IntakeLogsService(mock_supabase)
        log = await service.get_by_course_and_day(999, 1)

        assert log is None

    @pytest.mark.asyncio
    async def test_update_status(self, mock_supabase):
        """Обновляет статус."""
        from app.services.intake_logs import IntakeLogsService

        chain = create_supabase_chain()
        mock_supabase.table = MagicMock(return_value=chain)

        service = IntakeLogsService(mock_supabase)
        await service.update_status(course_id=1, day=5, status="taken")

        chain.update.assert_called_once()