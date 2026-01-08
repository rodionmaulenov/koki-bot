"""Тесты для workers/tasks.py."""
import pytest
from unittest.mock import AsyncMock, patch

from app.utils.time_utils import get_tashkent_now
from app import templates


class TestSendReminders:
    """Тесты для send_reminders."""

    @pytest.mark.asyncio
    async def test_sends_1h_reminder(
            self,
            supabase,
            redis,
            mock_bot,
            test_user_with_telegram,
    ):
        """Отправляет напоминание за 1 час."""
        from app.workers.tasks import _send_reminder

        now = get_tashkent_now()
        intake_hour = (now.hour + 1) % 24
        intake_time = f"{intake_hour:02d}:{now.minute:02d}"
        today = now.date().isoformat()

        await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": "test_reminder_1h",
            "status": "active",
            "start_date": today,
            "intake_time": intake_time,
            "current_day": 1,
        }).execute()

        with patch("app.workers.tasks.bot", mock_bot), \
                patch("app.workers.tasks.get_redis", AsyncMock(return_value=redis)):
            from app.utils.time_utils import calculate_time_range_before
            time_from, time_to = calculate_time_range_before(60)

            await _send_reminder(
                supabase, today, time_from, time_to, "1h", templates.REMINDER_1H
            )

        # Проверяем что сообщение отправлено
        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == test_user_with_telegram["telegram_id"]
        assert call_kwargs["text"] == templates.REMINDER_1H

        # Проверяем что Redis setex был вызван
        redis.setex.assert_called()

        # Cleanup
        await supabase.table("courses").delete().eq("invite_code", "test_reminder_1h").execute()

    @pytest.mark.asyncio
    async def test_no_duplicate_reminder(
            self,
            supabase,
            redis,
            mock_bot,
            test_user_with_telegram,
    ):
        """Не отправляет повторное напоминание."""
        from app.workers.tasks import _send_reminder

        now = get_tashkent_now()
        intake_hour = (now.hour + 1) % 24
        intake_time = f"{intake_hour:02d}:{now.minute:02d}"
        today = now.date().isoformat()

        result = await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": "test_no_duplicate",
            "status": "active",
            "start_date": today,
            "intake_time": intake_time,
            "current_day": 1,
        }).execute()

        course_id = result.data[0]["id"]

        # Эмулируем что ключ уже есть в Redis
        redis.exists = AsyncMock(return_value=True)  # <-- Вот исправление!

        with patch("app.workers.tasks.bot", mock_bot), \
                patch("app.workers.tasks.get_redis", AsyncMock(return_value=redis)):
            from app.utils.time_utils import calculate_time_range_before
            time_from, time_to = calculate_time_range_before(60)

            await _send_reminder(
                supabase, today, time_from, time_to, "1h", templates.REMINDER_1H
            )

        # Сообщение НЕ должно быть отправлено
        mock_bot.send_message.assert_not_called()

        # Cleanup
        await supabase.table("courses").delete().eq("id", course_id).execute()

class TestSendAlerts:
    """Тесты для send_alerts."""

    @pytest.mark.asyncio
    async def test_sends_alert_after_30min(
        self,
        supabase,
        redis,
        mock_bot,
        test_user_with_telegram,
    ):
        """Отправляет alert через 30 минут после пропуска."""
        from app.workers.tasks import send_alerts

        now = get_tashkent_now()
        # intake_time было 30 минут назад
        intake_minutes = now.hour * 60 + now.minute - 30
        if intake_minutes < 0:
            intake_minutes += 24 * 60
        intake_hour = intake_minutes // 60
        intake_minute = intake_minutes % 60
        intake_time = f"{intake_hour:02d}:{intake_minute:02d}"
        today = now.date().isoformat()

        result = await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": "test_alert_30min",
            "status": "active",
            "start_date": today,
            "intake_time": intake_time,
            "current_day": 1,
            "late_count": 0,
        }).execute()

        course_id = result.data[0]["id"]

        with patch("app.workers.tasks.bot", mock_bot), \
             patch("app.workers.tasks.get_redis", AsyncMock(return_value=redis)), \
             patch("app.workers.tasks.get_supabase", AsyncMock(return_value=supabase)):

            await send_alerts()

        # Проверяем что alert отправлен
        mock_bot.send_message.assert_called()
        call_kwargs = mock_bot.send_message.call_args[1]
        assert call_kwargs["text"] == templates.ALERT_30MIN

        # Проверяем что late_count увеличился
        updated = await supabase.table("courses") \
            .select("late_count") \
            .eq("id", course_id) \
            .single() \
            .execute()
        assert updated.data["late_count"] == 1

        # Cleanup
        key = f"sent:{course_id}:{today}:alert"
        await redis.delete(key)
        await supabase.table("courses").delete().eq("id", course_id).execute()

    @pytest.mark.asyncio
    async def test_no_alert_if_video_sent(
        self,
        supabase,
        redis,
        mock_bot,
        test_user_with_telegram,
        intake_logs_service,
    ):
        """Не отправляет alert если видео уже отправлено."""
        from app.workers.tasks import send_alerts

        now = get_tashkent_now()
        intake_minutes = now.hour * 60 + now.minute - 30
        if intake_minutes < 0:
            intake_minutes += 24 * 60
        intake_hour = intake_minutes // 60
        intake_minute = intake_minutes % 60
        intake_time = f"{intake_hour:02d}:{intake_minute:02d}"
        today = now.date().isoformat()

        result = await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": "test_no_alert_video",
            "status": "active",
            "start_date": today,
            "intake_time": intake_time,
            "current_day": 1,
        }).execute()

        course_id = result.data[0]["id"]

        # Девушка уже отправила видео
        await intake_logs_service.create(
            course_id=course_id,
            day=1,
            status="taken",
            video_file_id="test_video",
        )

        with patch("app.workers.tasks.bot", mock_bot), \
             patch("app.workers.tasks.get_redis", AsyncMock(return_value=redis)), \
             patch("app.workers.tasks.get_supabase", AsyncMock(return_value=supabase)):

            await send_alerts()

        # Alert НЕ должен быть отправлен
        mock_bot.send_message.assert_not_called()

        # Cleanup
        await supabase.table("intake_logs").delete().eq("course_id", course_id).execute()
        await supabase.table("courses").delete().eq("id", course_id).execute()


class TestSendRefusals:
    """Тесты для send_refusals."""

    @pytest.mark.asyncio
    async def test_refusal_3_delays(
        self,
        supabase,
        redis,
        mock_bot,
        test_user_with_telegram,
    ):
        """Завершает программу при 3 опозданиях."""
        from app.workers.tasks import send_refusals

        now = get_tashkent_now()
        today = now.date().isoformat()

        result = await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": "test_refusal_3delays",
            "status": "active",
            "start_date": today,
            "intake_time": "12:00",
            "current_day": 4,
            "late_count": 3,  # 3 опоздания
        }).execute()

        course_id = result.data[0]["id"]

        with patch("app.workers.tasks.bot", mock_bot), \
             patch("app.workers.tasks.get_redis", AsyncMock(return_value=redis)), \
             patch("app.workers.tasks.get_supabase", AsyncMock(return_value=supabase)):

            await send_refusals()

        # Проверяем что сообщение отправлено девушке (первый вызов)
        mock_bot.send_message.assert_called()
        first_call = mock_bot.send_message.call_args_list[0]
        assert first_call[1]["text"] == templates.REFUSAL_3_DELAYS

        # Проверяем что курс завершён
        updated = await supabase.table("courses") \
            .select("status") \
            .eq("id", course_id) \
            .single() \
            .execute()
        assert updated.data["status"] == "refused"

        # Cleanup
        key = f"sent:{course_id}:{today}:refusal_3delays"
        await redis.delete(key)
        await supabase.table("intake_logs").delete().eq("course_id", course_id).execute()
        await supabase.table("courses").delete().eq("id", course_id).execute()

    @pytest.mark.asyncio
    async def test_refusal_missed_2h(
        self,
        supabase,
        redis,
        mock_bot,
        test_user_with_telegram,
    ):
        """Завершает программу при пропуске >2 часов."""
        from app.workers.tasks import send_refusals

        now = get_tashkent_now()
        # intake_time было 2 часа назад
        intake_minutes = now.hour * 60 + now.minute - 120
        if intake_minutes < 0:
            intake_minutes += 24 * 60
        intake_hour = intake_minutes // 60
        intake_minute = intake_minutes % 60
        intake_time = f"{intake_hour:02d}:{intake_minute:02d}"
        today = now.date().isoformat()

        result = await supabase.table("courses").insert({
            "user_id": test_user_with_telegram["id"],
            "invite_code": "test_refusal_missed",
            "status": "active",
            "start_date": today,
            "intake_time": intake_time,
            "current_day": 1,
            "late_count": 0,
        }).execute()

        course_id = result.data[0]["id"]

        with patch("app.workers.tasks.bot", mock_bot), \
             patch("app.workers.tasks.get_redis", AsyncMock(return_value=redis)), \
             patch("app.workers.tasks.get_supabase", AsyncMock(return_value=supabase)):

            await send_refusals()

        # Проверяем что сообщение отправлено девушке (первый вызов)
        mock_bot.send_message.assert_called()
        first_call = mock_bot.send_message.call_args_list[0]
        assert first_call[1]["text"] == templates.REFUSAL_MISSED

        # Проверяем что курс завершён
        updated = await supabase.table("courses") \
            .select("status") \
            .eq("id", course_id) \
            .single() \
            .execute()
        assert updated.data["status"] == "refused"

        # Cleanup
        key = f"sent:{course_id}:{today}:refusal_missed"
        await redis.delete(key)
        await supabase.table("intake_logs").delete().eq("course_id", course_id).execute()
        await supabase.table("courses").delete().eq("id", course_id).execute()


class TestCleanupExpiredLinks:
    """Тесты для cleanup_expired_links."""

    @pytest.mark.asyncio
    async def test_deletes_expired_link(
        self,
        supabase,
        test_manager,
    ):
        """Удаляет просроченную ссылку (>24 часа)."""
        from app.workers.tasks import cleanup_expired_links
        from datetime import datetime, timedelta

        # Создаём user
        user_result = await supabase.table("users").insert({
            "name": "Просроченная Девушка",
            "manager_id": test_manager["id"],
        }).execute()
        user_id = user_result.data[0]["id"]

        # Создаём курс с датой >24 часа назад
        old_date = (datetime.now() - timedelta(hours=25)).isoformat()
        course_result = await supabase.table("courses").insert({
            "user_id": user_id,
            "invite_code": "expired_test_123",
            "status": "setup",
            "invite_used": False,
            "created_at": old_date,
        }).execute()
        course_id = course_result.data[0]["id"]

        # Запускаем очистку
        with patch("app.workers.tasks.get_supabase", AsyncMock(return_value=supabase)):
            await cleanup_expired_links()

        # Проверяем что курс удалён
        course_check = await supabase.table("courses") \
            .select("id") \
            .eq("id", course_id) \
            .execute()
        assert len(course_check.data) == 0

        # Проверяем что user удалён
        user_check = await supabase.table("users") \
            .select("id") \
            .eq("id", user_id) \
            .execute()
        assert len(user_check.data) == 0

    @pytest.mark.asyncio
    async def test_keeps_fresh_link(
        self,
        supabase,
        test_manager,
    ):
        """НЕ удаляет свежую ссылку (<24 часа)."""
        from app.workers.tasks import cleanup_expired_links

        # Создаём user
        user_result = await supabase.table("users").insert({
            "name": "Свежая Девушка",
            "manager_id": test_manager["id"],
        }).execute()
        user_id = user_result.data[0]["id"]

        # Создаём курс (created_at = сейчас, по умолчанию)
        course_result = await supabase.table("courses").insert({
            "user_id": user_id,
            "invite_code": "fresh_test_123",
            "status": "setup",
            "invite_used": False,
        }).execute()
        course_id = course_result.data[0]["id"]

        with patch("app.workers.tasks.get_supabase", AsyncMock(return_value=supabase)):
            await cleanup_expired_links()

        # Курс должен остаться
        course_check = await supabase.table("courses") \
            .select("id") \
            .eq("id", course_id) \
            .execute()
        assert len(course_check.data) == 1

        # Cleanup
        await supabase.table("courses").delete().eq("id", course_id).execute()
        await supabase.table("users").delete().eq("id", user_id).execute()

    @pytest.mark.asyncio
    async def test_keeps_used_link(
        self,
        supabase,
        test_manager,
    ):
        """НЕ удаляет использованную ссылку."""
        from app.workers.tasks import cleanup_expired_links
        from datetime import datetime, timedelta

        user_result = await supabase.table("users").insert({
            "name": "Использованная Девушка",
            "manager_id": test_manager["id"],
        }).execute()
        user_id = user_result.data[0]["id"]

        old_date = (datetime.now() - timedelta(hours=25)).isoformat()
        course_result = await supabase.table("courses").insert({
            "user_id": user_id,
            "invite_code": "used_test_123",
            "status": "setup",
            "invite_used": True,  # Использована!
            "created_at": old_date,
        }).execute()
        course_id = course_result.data[0]["id"]

        with patch("app.workers.tasks.get_supabase", AsyncMock(return_value=supabase)):
            await cleanup_expired_links()

        # Курс должен остаться
        course_check = await supabase.table("courses") \
            .select("id") \
            .eq("id", course_id) \
            .execute()
        assert len(course_check.data) == 1

        # Cleanup
        await supabase.table("courses").delete().eq("id", course_id).execute()
        await supabase.table("users").delete().eq("id", user_id).execute()

    @pytest.mark.asyncio
    async def test_keeps_active_course(
        self,
        supabase,
        test_manager,
    ):
        """НЕ удаляет активный курс."""
        from app.workers.tasks import cleanup_expired_links
        from datetime import datetime, timedelta

        user_result = await supabase.table("users").insert({
            "name": "Активная Девушка",
            "manager_id": test_manager["id"],
        }).execute()
        user_id = user_result.data[0]["id"]

        old_date = (datetime.now() - timedelta(hours=25)).isoformat()
        course_result = await supabase.table("courses").insert({
            "user_id": user_id,
            "invite_code": "active_test_123",
            "status": "active",  # Активный!
            "invite_used": True,
            "created_at": old_date,
        }).execute()
        course_id = course_result.data[0]["id"]

        with patch("app.workers.tasks.get_supabase", AsyncMock(return_value=supabase)):
            await cleanup_expired_links()

        # Курс должен остаться
        course_check = await supabase.table("courses") \
            .select("id") \
            .eq("id", course_id) \
            .execute()
        assert len(course_check.data) == 1

        # Cleanup
        await supabase.table("courses").delete().eq("id", course_id).execute()
        await supabase.table("users").delete().eq("id", user_id).execute()

    @pytest.mark.asyncio
    async def test_keeps_user_with_other_courses(
        self,
        supabase,
        test_manager,
    ):
        """Удаляет курс, но НЕ удаляет user если есть другой курс."""
        from app.workers.tasks import cleanup_expired_links
        from datetime import datetime, timedelta

        user_result = await supabase.table("users").insert({
            "name": "Девушка С Двумя Курсами",
            "manager_id": test_manager["id"],
        }).execute()
        user_id = user_result.data[0]["id"]

        old_date = (datetime.now() - timedelta(hours=25)).isoformat()

        # Старый просроченный курс
        expired_course = await supabase.table("courses").insert({
            "user_id": user_id,
            "invite_code": "expired_course",
            "status": "setup",
            "invite_used": False,
            "created_at": old_date,
        }).execute()
        expired_course_id = expired_course.data[0]["id"]

        # Активный курс
        active_course = await supabase.table("courses").insert({
            "user_id": user_id,
            "invite_code": "active_course",
            "status": "active",
            "invite_used": True,
        }).execute()
        active_course_id = active_course.data[0]["id"]

        with patch("app.workers.tasks.get_supabase", AsyncMock(return_value=supabase)):
            await cleanup_expired_links()

        # Просроченный курс удалён
        expired_check = await supabase.table("courses") \
            .select("id") \
            .eq("id", expired_course_id) \
            .execute()
        assert len(expired_check.data) == 0

        # Активный курс остался
        active_check = await supabase.table("courses") \
            .select("id") \
            .eq("id", active_course_id) \
            .execute()
        assert len(active_check.data) == 1

        # User остался (есть другой курс)
        user_check = await supabase.table("users") \
            .select("id") \
            .eq("id", user_id) \
            .execute()
        assert len(user_check.data) == 1

        # Cleanup
        await supabase.table("courses").delete().eq("id", active_course_id).execute()
        await supabase.table("users").delete().eq("id", user_id).execute()