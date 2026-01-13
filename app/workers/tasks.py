"""Периодические задачи для напоминаний и проверок."""
from datetime import timedelta

from app.services.courses import CourseService
from app.services.dashboard import DashboardService
from app.services.managers import ManagerService
from app.services.topic import TopicService
from app.config import get_settings
from app.services.users import UserService
from app.workers.broker import broker, get_redis
from app.workers.database import get_supabase
from app.workers.bot import bot
from app.services.intake_logs import IntakeLogsService
from app.utils.time_utils import (
    get_tashkent_now,
    calculate_time_range_before,
    calculate_time_range_after,
    format_date,
)
from app import templates

# TTL для Redis ключей — 24 часа
REDIS_TTL = 86400


async def was_sent(course_id: int, reminder_type: str) -> bool:
    """Проверяет отправляли ли уже это напоминание сегодня."""
    redis = await get_redis()
    today = get_tashkent_now().date().isoformat()
    key = f"sent:{course_id}:{today}:{reminder_type}"
    return await redis.exists(key)


async def mark_sent(course_id: int, reminder_type: str) -> None:
    """Отмечает что напоминание отправлено."""
    redis = await get_redis()
    today = get_tashkent_now().date().isoformat()
    key = f"sent:{course_id}:{today}:{reminder_type}"
    await redis.setex(key, REDIS_TTL, "1")


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def send_reminders():
    """Отправляет напоминания за 60 и 10 минут до приёма."""
    supabase = await get_supabase()
    course_service = CourseService(supabase)
    user_service = UserService(supabase)

    today = get_tashkent_now().date().isoformat()

    # Напоминание за 60 минут
    time_from, time_to = calculate_time_range_before(60)
    await _send_reminder(course_service, user_service, today, time_from, time_to, "1h", templates.REMINDER_1H)

    # Напоминание за 10 минут
    time_from, time_to = calculate_time_range_before(10)
    await _send_reminder(course_service, user_service, today, time_from, time_to, "10min", templates.REMINDER_10MIN)


async def _send_reminder(
    course_service: CourseService,
    user_service: UserService,
    today: str,
    time_from: str,
    time_to: str,
    reminder_type: str,
    text: str,
):
    """Отправляет напоминания для курсов в указанном диапазоне времени."""
    courses = await course_service.get_active_by_intake_time(today, time_from, time_to)

    for course in courses:
        course_id = course["id"]

        # Уже отправляли?
        if await was_sent(course_id, reminder_type):
            continue

        # Получаем telegram_id
        telegram_id = await user_service.get_telegram_id(course["user_id"])
        if not telegram_id:
            continue

        # Отправляем
        try:
            await bot.send_message(chat_id=telegram_id, text=text)
            await mark_sent(course_id, reminder_type)
            print(f"📬 Reminder {reminder_type} → {telegram_id}")
        except Exception as e:
            print(f"❌ Reminder failed: {e}")


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def send_alerts():
    """Отправляет предупреждения через 30 минут после пропуска.
    Если это 3-е опоздание — сразу завершает программу.
    """
    settings = get_settings()
    supabase = await get_supabase()

    course_service = CourseService(supabase)
    user_service = UserService(supabase)
    manager_service = ManagerService(supabase)
    intake_logs_service = IntakeLogsService(supabase)
    dashboard_service = DashboardService(supabase, settings.kok_group_id)
    topic_service = TopicService(bot, settings.kok_group_id)

    today = get_tashkent_now().date().isoformat()
    time_from, time_to = calculate_time_range_after(30)

    courses = await course_service.get_active_by_intake_time(today, time_from, time_to)
    any_refusal = False

    for course in courses:
        course_id = course["id"]

        # Уже отправляли alert?
        if await was_sent(course_id, "alert"):
            continue

        # Проверяем что текущее время больше intake_time (не ночной переход)
        intake_time = course.get("intake_time", "")[:5]
        now = get_tashkent_now()
        current_time = f"{now.hour:02d}:{now.minute:02d}"
        if current_time < intake_time:
            continue

        # Есть ли видео сегодня?
        has_video_today = await intake_logs_service.has_log_today(course_id)
        if has_video_today:
            continue

        # Получаем user через сервис
        user_data = await user_service.get_by_id(course["user_id"])
        if not user_data:
            continue

        telegram_id = user_data.get("telegram_id")
        if not telegram_id:
            continue

        # Увеличиваем счётчик опозданий через сервис
        late_count = course.get("late_count", 0) + 1
        await course_service.update(course_id, late_count=late_count)

        await mark_sent(course_id, "alert")

        # Если 3-е опоздание — сразу завершаем программу
        if late_count >= 3:
            current_day = course.get("current_day", 1)
            total_days = course.get("total_days") or 21

            await course_service.set_refused(course_id)

            # Закрываем топик
            topic_id = user_data.get("topic_id")
            if topic_id:
                manager = await manager_service.get_by_id(user_data.get("manager_id"))
                manager_name = manager.get("name", "") if manager else ""

                await topic_service.rename_topic_on_close(
                    topic_id=topic_id,
                    girl_name=user_data.get("name", ""),
                    manager_name=manager_name,
                    completed_days=current_day - 1,
                    total_days=total_days,
                    status="refused",
                )

                if course.get("registration_message_id"):
                    await topic_service.remove_registration_buttons(
                        message_id=course["registration_message_id"],
                        cycle_day=course.get("cycle_day", 1),
                        intake_time=course.get("intake_time", ""),
                        start_date=format_date(course.get("start_date", "")),
                    )

                await topic_service.send_closure_message(
                    topic_id=topic_id,
                    status="refused",
                    reason=templates.REFUSAL_REASON_3_DELAYS,
                )

                await topic_service.close_topic(topic_id)

            # Записываем в intake_logs
            await intake_logs_service.create(
                course_id=course_id,
                day=current_day,
                status="missed",
                video_file_id="",
            )

            # Отправляем сообщение девушке
            try:
                await bot.send_message(chat_id=telegram_id, text=templates.REFUSAL_3_DELAYS)
                print(f"🚫 Refusal (3delays) → {telegram_id}")
                any_refusal = True
            except Exception as e:
                print(f"❌ Refusal message failed: {e}")

            continue

        # Иначе просто отправляем alert
        try:
            await bot.send_message(chat_id=telegram_id, text=templates.ALERT_30MIN)
            print(f"🚨 Alert → {telegram_id}, late_count={late_count}")
        except Exception as e:
            print(f"❌ Alert failed: {e}")

    # Обновляем дашборд если были отказы
    if any_refusal:
        await dashboard_service.update_dashboard(bot, settings.general_thread_id)


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def send_refusals():
    """Завершает программу при пропуске более 2 часов."""
    settings = get_settings()
    supabase = await get_supabase()

    course_service = CourseService(supabase)
    user_service = UserService(supabase)
    manager_service = ManagerService(supabase)
    intake_logs_service = IntakeLogsService(supabase)
    dashboard_service = DashboardService(supabase, settings.kok_group_id)
    topic_service = TopicService(bot, settings.kok_group_id)

    today = get_tashkent_now().date().isoformat()
    time_from, time_to = calculate_time_range_after(120)

    courses = await course_service.get_active_by_intake_time(today, time_from, time_to)
    any_refusal = False

    for course in courses:
        course_id = course["id"]
        current_day = course.get("current_day", 1)
        total_days = course.get("total_days") or 21

        # Проверяем что текущее время больше intake_time (не ночной переход)
        intake_time = course.get("intake_time", "")[:5]
        now = get_tashkent_now()
        current_time = f"{now.hour:02d}:{now.minute:02d}"
        if current_time < intake_time:
            continue

        # Есть ли видео сегодня?
        has_video_today = await intake_logs_service.has_log_today(course_id)
        if has_video_today:
            continue

        # Уже обрабатывали?
        if await was_sent(course_id, "refusal_missed"):
            continue

        # Завершаем курс
        await course_service.set_refused(course_id)

        # Закрываем топик с полной последовательностью
        user = await user_service.get_by_id(course["user_id"])
        topic_id = user.get("topic_id") if user else None
        if topic_id:
            manager = await manager_service.get_by_id(user["manager_id"])
            manager_name = manager.get("name", "") if manager else ""

            await topic_service.rename_topic_on_close(
                topic_id=topic_id,
                girl_name=user.get("name", ""),
                manager_name=manager_name,
                completed_days=current_day - 1,
                total_days=total_days,
                status="refused",
            )

            if course.get("registration_message_id"):
                await topic_service.remove_registration_buttons(
                    message_id=course["registration_message_id"],
                    cycle_day=course.get("cycle_day", 1),
                    intake_time=course.get("intake_time", ""),
                    start_date=format_date(course.get("start_date", "")),
                )

            await topic_service.send_closure_message(
                topic_id=topic_id,
                status="refused",
                reason=templates.REFUSAL_REASON_MISSED,
            )

            await topic_service.close_topic(topic_id)

        # Записываем в intake_logs
        await intake_logs_service.create(
            course_id=course_id,
            day=current_day,
            status="missed",
            video_file_id="",
        )

        await mark_sent(course_id, "refusal_missed")

        # Отправляем сообщение
        telegram_id = await user_service.get_telegram_id(course["user_id"])
        if telegram_id:
            try:
                await bot.send_message(chat_id=telegram_id, text=templates.REFUSAL_MISSED)
                print(f"🚫 Refusal (missed) → {telegram_id}")
                any_refusal = True
            except Exception as e:
                print(f"❌ Refusal failed: {e}")

    # Обновляем дашборд если были отказы
    if any_refusal:
        await dashboard_service.update_dashboard(bot, settings.general_thread_id)


@broker.task(schedule=[{"cron": "0 3 * * *"}])  # 3:00 ночи каждый день
async def cleanup_expired_links():
    """Удаляет неиспользованные ссылки старше 24 часов."""
    supabase = await get_supabase()
    course_service = CourseService(supabase)
    user_service = UserService(supabase)

    # 24 часа назад
    now = get_tashkent_now()
    threshold = (now - timedelta(hours=24)).isoformat()

    # Находим просроченные курсы
    expired_courses = await course_service.get_expired_setup(threshold)
    deleted_count = 0

    for course in expired_courses:
        course_id = course["id"]
        user_id = course["user_id"]

        try:
            # Удаляем course
            await course_service.delete(course_id)

            # Удаляем user (если нет других курсов)
            other_count = await course_service.count_by_user_id(user_id)
            if other_count == 0:
                await user_service.delete(user_id)

            deleted_count += 1
        except Exception as e:
            print(f"❌ Cleanup failed for course {course_id}: {e}")

    if deleted_count:
        print(f"🧹 Cleaned up {deleted_count} expired links")


@broker.task(schedule=[{"cron": "* * * * *"}])
async def refresh_dashboard():
    """Обновляет единый дашборд КОК."""
    settings = get_settings()
    supabase = await get_supabase()

    dashboard_service = DashboardService(
        supabase=supabase,
        kok_group_id=settings.kok_group_id,
    )

    await dashboard_service.update_dashboard(
        bot=bot,
        thread_id=settings.general_thread_id,
    )