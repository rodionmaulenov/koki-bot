"""Тесты для DashboardService."""
import pytest
import secrets

from app.utils.time_utils import get_tashkent_now


class TestDashboardService:
    """Тесты для сервиса дашбордов."""

    @pytest.fixture
    def dashboard_service(self, supabase):
        """Создаёт DashboardService."""
        from app.services.dashboard import DashboardService
        return DashboardService(supabase=supabase, group_chat_id=-1001234567890)

    @pytest.mark.asyncio
    async def test_generate_active_courses_empty(self, dashboard_service, supabase):
        """Пустой дашборд если нет активных курсов."""
        # Удаляем все активные курсы для чистоты теста
        await supabase.table("courses").delete().eq("status", "active").execute()

        text = await dashboard_service.generate_active_courses()

        assert "📊 Активные курсы" in text
        assert "Всего: 0" in text

    @pytest.mark.asyncio
    async def test_generate_active_courses_with_data(
        self,
        dashboard_service,
        supabase,
        test_manager,
        test_user_with_telegram,
        test_active_course,
    ):
        """Дашборд с активными курсами."""
        text = await dashboard_service.generate_active_courses()

        assert "📊 Активные курсы" in text
        assert "Всего:" in text
        assert test_user_with_telegram["name"] in text

    @pytest.mark.asyncio
    async def test_generate_active_courses_shows_sent_today(
        self,
        dashboard_service,
        supabase,
        test_manager,
        test_user_with_telegram,
        test_active_course,
        intake_logs_service,
    ):
        """Показывает ✅ если сегодня отправила."""
        # Добавляем запись что видео отправлено
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=test_active_course["current_day"],
            status="taken",
            video_file_id="test_video",
        )

        text = await dashboard_service.generate_active_courses()

        assert "✅" in text

        # Cleanup
        await supabase.table("intake_logs").delete().eq("course_id", test_active_course["id"]).execute()

    @pytest.mark.asyncio
    async def test_generate_active_courses_shows_late_warning(
        self,
        dashboard_service,
        supabase,
        test_manager,
        test_user_with_telegram,
    ):
        """Показывает ⚠️ при опозданиях."""
        today = get_tashkent_now().date().isoformat()
        course = await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": secrets.token_urlsafe(8),
            "status": "active",
            "start_date": today,
            "current_day": 5,
            "late_count": 2,
            "intake_time": "12:00",
        }).execute()
        course_id = course.data[0]["id"]

        text = await dashboard_service.generate_active_courses()

        assert "⚠️" in text
        assert "(2)" in text

        # Cleanup
        await supabase.table("courses").delete().eq("id", course_id).execute()

    @pytest.mark.asyncio
    async def test_generate_refusals_empty(self, dashboard_service, supabase):
        """Пустой дашборд если нет отказов."""
        # Удаляем все refused курсы
        await supabase.table("courses").delete().eq("status", "refused").execute()

        text = await dashboard_service.generate_refusals(days=10)

        assert "🚫 Отказы" in text
        assert "Всего: 0" in text

    @pytest.mark.asyncio
    async def test_generate_refusals_with_data(
        self,
        dashboard_service,
        supabase,
        test_manager,
        test_user_with_telegram,
    ):
        """Дашборд с отказами."""
        course = await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": secrets.token_urlsafe(8),
            "status": "refused",
            "current_day": 5,
            "late_count": 0,
        }).execute()
        course_id = course.data[0]["id"]

        text = await dashboard_service.generate_refusals(days=10)

        assert "🚫 Отказы" in text
        assert test_user_with_telegram["name"] in text
        assert "пропуск" in text

        # Cleanup
        await supabase.table("courses").delete().eq("id", course_id).execute()

    @pytest.mark.asyncio
    async def test_generate_refusals_shows_3_delays(
        self,
        dashboard_service,
        supabase,
        test_manager,
        test_user_with_telegram,
    ):
        """Показывает причину '3 опоздания'."""
        course = await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": secrets.token_urlsafe(8),
            "status": "refused",
            "current_day": 8,
            "late_count": 3,
        }).execute()
        course_id = course.data[0]["id"]

        text = await dashboard_service.generate_refusals(days=10)

        assert "3 опоздания" in text

        # Cleanup
        await supabase.table("courses").delete().eq("id", course_id).execute()

    def test_format_date(self, dashboard_service):
        """Форматирует дату правильно."""
        result = dashboard_service._format_date("2026-01-06")
        assert result == "6 Янв"

        result = dashboard_service._format_date("2026-12-25")
        assert result == "25 Дек"

    def test_make_topic_link_with_topic(self, dashboard_service):
        """Создаёт кликабельную ссылку."""
        result = dashboard_service._make_topic_link(123, "Иванова Мария")

        assert "Иванова Мария" in result
        assert "href=" in result
        assert "t.me/c/" in result

    def test_make_topic_link_without_topic(self, dashboard_service):
        """Возвращает имя без ссылки если нет topic_id."""
        result = dashboard_service._make_topic_link(None, "Иванова Мария")

        assert result == "Иванова Мария"
        assert "href" not in result

    @pytest.mark.asyncio
    async def test_generate_active_courses_shows_pending_review(
            self,
            dashboard_service,
            supabase,
            test_manager,
            test_user_with_telegram,
            test_active_course,
            intake_logs_service,
    ):
        """Показывает секцию 'Ждёт проверки' если есть pending_review."""
        # Добавляем запись с pending_review
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=test_active_course["current_day"],
            status="pending_review",
            video_file_id="test_video",
        )

        text = await dashboard_service.generate_active_courses()

        assert "⏳ Ждёт проверки" in text
        assert test_user_with_telegram["name"] in text

        # Cleanup
        await supabase.table("intake_logs").delete().eq("course_id", test_active_course["id"]).execute()