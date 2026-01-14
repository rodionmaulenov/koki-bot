"""Тесты для DashboardService."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from app.services.dashboard import DashboardService, SEPARATOR


class TestDashboardService:
    """Тесты для сервиса дашбордов."""

    @pytest.fixture
    def dashboard_service(self, mock_supabase):
        """Создаёт DashboardService с моком."""
        return DashboardService(supabase=mock_supabase, kok_group_id=-1003663830211)

    # =========================================================================
    # ТЕСТЫ ФОРМАТИРОВАНИЯ
    # =========================================================================

    def test_format_date(self, dashboard_service):
        """Форматирует дату правильно."""
        assert dashboard_service._format_date("2026-01-06") == "6 Янв"
        assert dashboard_service._format_date("2026-12-25") == "25 Дек"
        assert dashboard_service._format_date("2026-07-15") == "15 Июл"

    def test_format_time(self, dashboard_service):
        """Форматирует время правильно."""
        assert dashboard_service._format_time("14:30:00") == "14:30"
        assert dashboard_service._format_time("09:05") == "09:05"
        assert dashboard_service._format_time(None) == "—"
        assert dashboard_service._format_time("") == "—"

    def test_make_topic_link_with_topic(self, dashboard_service):
        """Создаёт кликабельную ссылку."""
        result = dashboard_service._make_topic_link(123, "Иванова Мария Петровна")

        assert "Иванова М. П." in result
        assert "href=" in result
        assert "t.me/c/3663830211/123" in result

    def test_make_topic_link_without_topic(self, dashboard_service):
        """Возвращает имя без ссылки если нет topic_id."""
        result = dashboard_service._make_topic_link(None, "Иванова Мария")

        assert result == "Иванова Мария"
        assert "href" not in result

    # =========================================================================
    # ТЕСТЫ ГЕНЕРАЦИИ ДАШБОРДА
    # =========================================================================

    @pytest.mark.asyncio
    async def test_generate_full_dashboard_empty(self, mock_supabase):
        """Генерация пустого дашборда."""
        def create_empty_chain():
            chain = MagicMock()
            chain.select = MagicMock(return_value=chain)
            chain.eq = MagicMock(return_value=chain)
            chain.gte = MagicMock(return_value=chain)
            chain.lte = MagicMock(return_value=chain)
            chain.in_ = MagicMock(return_value=chain)
            result = MagicMock()
            result.data = []
            chain.execute = AsyncMock(return_value=result)
            return chain

        mock_supabase.table = MagicMock(side_effect=lambda name: create_empty_chain())

        service = DashboardService(supabase=mock_supabase, kok_group_id=-1003663830211)
        text = await service.generate_full_dashboard()

        assert "📊 <b>КОК</b>" in text
        assert "💊 <b>Активные</b>" in text
        assert "❌ <b>Отказы</b>" in text
        assert "✅ <b>Завершили</b>" in text
        assert "— пусто —" in text
        assert SEPARATOR in text

    @pytest.mark.asyncio
    async def test_generate_active_section_with_data(self, mock_supabase):
        """Генерация секции активных с данными."""
        courses_data = [{
            "id": 1,
            "current_day": 5,
            "total_days": 21,
            "intake_time": "12:00:00",
            "late_count": 0,
            "users": {
                "name": "Тестова Мария Ивановна",
                "topic_id": 123,
                "managers": {"name": "Rodion"}
            }
        }]

        def create_chain(table_name):
            chain = MagicMock()
            chain.select = MagicMock(return_value=chain)
            chain.eq = MagicMock(return_value=chain)
            chain.gte = MagicMock(return_value=chain)
            chain.lte = MagicMock(return_value=chain)
            chain.in_ = MagicMock(return_value=chain)

            result = MagicMock()
            if table_name == "courses":
                result.data = courses_data
            else:
                result.data = []
            chain.execute = AsyncMock(return_value=result)
            return chain

        mock_supabase.table = MagicMock(side_effect=create_chain)

        service = DashboardService(supabase=mock_supabase, kok_group_id=-1003663830211)
        lines = await service._generate_active_section()
        text = "\n".join(lines)

        assert "💊 <b>Активные</b>" in text
        assert "👩‍💼 Rodion" in text
        assert "Тестова М. И." in text
        assert "4/21" in text
        assert "12:00" in text

    @pytest.mark.asyncio
    async def test_active_section_shows_icons(self, mock_supabase):
        """Проверяет иконки статуса в активных."""
        courses_data = [
            {
                "id": 1, "current_day": 5, "total_days": 21, "intake_time": "12:00",
                "late_count": 0,
                "users": {"name": "Девушка 1", "topic_id": 1, "managers": {"name": "Manager"}}
            },
            {
                "id": 2, "current_day": 3, "total_days": 21, "intake_time": "14:00",
                "late_count": 2,
                "users": {"name": "Девушка 2", "topic_id": 2, "managers": {"name": "Manager"}}
            },
        ]

        intake_logs_data = [
            {"course_id": 1, "status": "taken"},
        ]

        def create_chain(table_name):
            chain = MagicMock()
            chain.select = MagicMock(return_value=chain)
            chain.eq = MagicMock(return_value=chain)
            chain.gte = MagicMock(return_value=chain)
            chain.lte = MagicMock(return_value=chain)
            chain.in_ = MagicMock(return_value=chain)

            result = MagicMock()
            if table_name == "courses":
                result.data = courses_data
            elif table_name == "intake_logs":
                result.data = intake_logs_data
            else:
                result.data = []
            chain.execute = AsyncMock(return_value=result)
            return chain

        mock_supabase.table = MagicMock(side_effect=create_chain)

        service = DashboardService(supabase=mock_supabase, kok_group_id=-1003663830211)
        lines = await service._generate_active_section()
        text = "\n".join(lines)

        assert "✅" in text
        assert "⚠️" in text

    @pytest.mark.asyncio
    async def test_refusals_section_with_reasons(self, mock_supabase):
        """Проверяет причины отказов."""
        courses_data = [
            {
                "id": 1, "current_day": 5, "late_count": 3, "created_at": "2026-01-10",
                "users": {"name": "Девушка 1", "topic_id": 1, "managers": {"name": "Manager"}}
            },
            {
                "id": 2, "current_day": 3, "late_count": 0, "created_at": "2026-01-09",
                "users": {"name": "Девушка 2", "topic_id": 2, "managers": {"name": "Manager"}}
            },
        ]

        def create_chain(table_name):
            chain = MagicMock()
            chain.select = MagicMock(return_value=chain)
            chain.eq = MagicMock(return_value=chain)
            chain.gte = MagicMock(return_value=chain)

            result = MagicMock()
            result.data = courses_data if table_name == "courses" else []
            chain.execute = AsyncMock(return_value=result)
            return chain

        mock_supabase.table = MagicMock(side_effect=create_chain)

        service = DashboardService(supabase=mock_supabase, kok_group_id=-1003663830211)
        lines = await service._generate_refusals_section(date.today(), days=10)
        text = "\n".join(lines)

        assert "❌ <b>Отказы</b>" in text
        assert "3 опоздания" in text
        assert "пропуск" in text

    @pytest.mark.asyncio
    async def test_completed_section_grouped_by_month(self, mock_supabase):
        """Проверяет группировку завершённых по месяцам."""
        courses_data = [
            {
                "id": 1, "total_days": 21, "created_at": "2026-01-10",
                "users": {"name": "Девушка 1", "topic_id": 1, "managers": {"name": "Manager"}}
            },
        ]

        def create_chain(table_name):
            chain = MagicMock()
            chain.select = MagicMock(return_value=chain)
            chain.eq = MagicMock(return_value=chain)
            chain.gte = MagicMock(return_value=chain)

            result = MagicMock()
            result.data = courses_data if table_name == "courses" else []
            chain.execute = AsyncMock(return_value=result)
            return chain

        mock_supabase.table = MagicMock(side_effect=create_chain)

        service = DashboardService(supabase=mock_supabase, kok_group_id=-1003663830211)
        lines = await service._generate_completed_section(date(2026, 1, 10))
        text = "\n".join(lines)

        assert "✅ <b>Завершили</b>" in text
        assert "Янв - 1" in text

    @pytest.mark.asyncio
    async def test_get_totals(self, mock_supabase):
        """Проверяет подсчёт итогов."""
        courses_data = [
            {"status": "active"},
            {"status": "active"},
            {"status": "completed"},
            {"status": "refused"},
        ]

        def create_chain(table_name):
            chain = MagicMock()
            chain.select = MagicMock(return_value=chain)

            result = MagicMock()
            result.data = courses_data
            chain.execute = AsyncMock(return_value=result)
            return chain

        mock_supabase.table = MagicMock(side_effect=create_chain)

        service = DashboardService(supabase=mock_supabase, kok_group_id=-1003663830211)
        totals = await service._get_totals()

        assert totals["active"] == 2
        assert totals["completed"] == 1
        assert totals["refused"] == 1