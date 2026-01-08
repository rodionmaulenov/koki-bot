"""Тесты для шаблонов сообщений."""

from app import templates


class TestTemplatesWithTotalDays:
    """Тесты что шаблоны корректно отображают total_days."""

    def test_already_on_course(self):
        """ALREADY_ON_COURSE содержит total_days."""
        result = templates.ALREADY_ON_COURSE.format(
            girl_name="Тест",
            current_day=5,
            total_days=42,
            intake_time="10:00",
        )
        assert "5/42" in result

    def test_topic_name(self):
        """TOPIC_NAME содержит total_days."""
        result = templates.TOPIC_NAME.format(
            girl_name="Иванова",
            manager_name="Менеджер",
            completed_days=10,
            total_days=42,
        )
        assert "10/42" in result

    def test_topic_day_complete(self):
        """TOPIC_DAY_COMPLETE содержит total_days."""
        result = templates.TOPIC_DAY_COMPLETE.format(day=15, total_days=42)
        assert "15/42" in result

    def test_video_accepted(self):
        """VIDEO_ACCEPTED содержит total_days."""
        result = templates.VIDEO_ACCEPTED.format(day=20, total_days=42)
        assert "20/42" in result

    def test_topic_review_request(self):
        """TOPIC_REVIEW_REQUEST содержит total_days."""
        result = templates.TOPIC_REVIEW_REQUEST.format(
            day=18,
            total_days=42,
            reason="низкая уверенность",
        )
        assert "18/42" in result

    def test_manager_video_approved(self):
        """MANAGER_VIDEO_APPROVED содержит total_days."""
        result = templates.MANAGER_VIDEO_APPROVED.format(day=21, total_days=42)
        assert "21/42" in result

    def test_manager_video_rejected(self):
        """MANAGER_VIDEO_REJECTED содержит total_days."""
        result = templates.MANAGER_VIDEO_REJECTED.format(day=19, total_days=42)
        assert "19/42" in result

    def test_manager_course_completed(self):
        """MANAGER_COURSE_COMPLETED содержит total_days."""
        result = templates.MANAGER_COURSE_COMPLETED.format(
            girl_name="Тест",
            day=18,
            total_days=42,
        )
        assert "18/42" in result


class TestExtendedCourseTemplates:
    """Тесты для шаблонов продления курса."""

    def test_course_extended(self):
        """COURSE_EXTENDED содержит total_days."""
        result = templates.COURSE_EXTENDED.format(total_days=42)
        assert "42" in result

    def test_manager_course_extended(self):
        """MANAGER_COURSE_EXTENDED содержит girl_name и total_days."""
        result = templates.MANAGER_COURSE_EXTENDED.format(
            girl_name="Иванова",
            total_days=42,
        )
        assert "Иванова" in result
        assert "42" in result


class TestDefaultTotalDays:
    """Тесты что шаблоны работают с дефолтным total_days=21."""

    def test_already_on_course_default(self):
        """ALREADY_ON_COURSE с total_days=21."""
        result = templates.ALREADY_ON_COURSE.format(
            girl_name="Тест",
            current_day=5,
            total_days=21,
            intake_time="10:00",
        )
        assert "5/21" in result

    def test_video_accepted_default(self):
        """VIDEO_ACCEPTED с total_days=21."""
        result = templates.VIDEO_ACCEPTED.format(day=20, total_days=21)
        assert "20/21" in result