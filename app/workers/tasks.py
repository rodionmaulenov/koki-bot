"""Периодические задачи для напоминаний и проверок."""
from datetime import timedelta

from app.services.courses import CourseService
from app.services.dashboard import DashboardService
from app.config import get_settings
from app.services.stats_messages import StatsMessagesService
from app.services.users import UserService
from app.workers.broker import broker, get_redis
from app.workers.database import get_supabase
from app.workers.bot import bot
from app.services.intake_logs import IntakeLogsService
from app.utils.time_utils import (
    get_tashkent_now,
    calculate_time_range_before,
    calculate_time_range_after,
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
    today = get_tashkent_now().date().isoformat()

    # Напоминание за 60 минут
    time_from, time_to = calculate_time_range_before(60)
    await _send_reminder(supabase, today, time_from, time_to, "1h", templates.REMINDER_1H)

    # Напоминание за 10 минут
    time_from, time_to = calculate_time_range_before(10)
    await _send_reminder(supabase, today, time_from, time_to, "10min", templates.REMINDER_10MIN)


async def _send_reminder(supabase, today: str, time_from: str, time_to: str, reminder_type: str, text: str):
    """Отправляет напоминания для курсов в указанном диапазоне времени."""
    result = await supabase.table("courses") \
        .select("id, user_id, intake_time") \
        .eq("status", "active") \
        .lte("start_date", today) \
        .gte("intake_time", time_from) \
        .lte("intake_time", time_to) \
        .execute()

    for course in result.data or []:
        course_id = course["id"]

        # Уже отправляли?
        if await was_sent(course_id, reminder_type):
            continue

        # Получаем telegram_id
        user = await supabase.table("users") \
            .select("telegram_id") \
            .eq("id", course["user_id"]) \
            .single() \
            .execute()

        telegram_id = user.data.get("telegram_id") if user.data else None
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
    """Отправляет предупреждения через 30 минут после пропуска."""
    supabase = await get_supabase()
    intake_logs_service = IntakeLogsService(supabase)
    today = get_tashkent_now().date().isoformat()

    time_from, time_to = calculate_time_range_after(30)

    result = await supabase.table("courses") \
        .select("id, user_id, current_day, late_count, intake_time") \
        .eq("status", "active") \
        .lte("start_date", today) \
        .gte("intake_time", time_from) \
        .lte("intake_time", time_to) \
        .execute()

    for course in result.data or []:
        course_id = course["id"]

        # Уже отправляли?
        if await was_sent(course_id, "alert"):
            continue

        # Есть ли видео сегодня?
        current_day = course.get("current_day", 1)
        existing_log = await intake_logs_service.get_by_course_and_day(course_id, current_day)
        if existing_log:
            continue

        # Получаем telegram_id
        user = await supabase.table("users") \
            .select("telegram_id") \
            .eq("id", course["user_id"]) \
            .single() \
            .execute()

        telegram_id = user.data.get("telegram_id") if user.data else None
        if not telegram_id:
            continue

        # Отправляем alert
        try:
            await bot.send_message(chat_id=telegram_id, text=templates.ALERT_30MIN)
            await mark_sent(course_id, "alert")

            # Увеличиваем счётчик опозданий
            late_count = course.get("late_count", 0) + 1
            await supabase.table("courses") \
                .update({"late_count": late_count}) \
                .eq("id", course_id) \
                .execute()

            print(f"🚨 Alert → {telegram_id}, late_count={late_count}")
        except Exception as e:
            print(f"❌ Alert failed: {e}")


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def send_refusals():
    """Завершает программу при 3 опозданиях или пропуске >2 часов."""
    settings = get_settings()
    supabase = await get_supabase()

    course_service = CourseService(supabase)
    user_service = UserService(supabase)
    intake_logs_service = IntakeLogsService(supabase)
    dashboard_service = DashboardService(supabase, settings.manager_group_id)

    today = get_tashkent_now().date().isoformat()
    time_from, time_to = calculate_time_range_after(120)

    courses = await course_service.get_active_started(today)
    any_refusal = False

    for course in courses:
        course_id = course["id"]
        current_day = course.get("current_day", 1)

        # Определяем причину отказа
        refusal_reason = None
        text = None

        # 3 опоздания подряд?
        if course.get("late_count", 0) >= 3:
            refusal_reason = "3delays"
            text = templates.REFUSAL_3_DELAYS

        # Прошло 2 часа без видео?
        intake_time = course.get("intake_time", "")[:5]
        if time_from <= intake_time <= time_to:
            existing_log = await intake_logs_service.get_by_course_and_day(course_id, current_day)
            if not existing_log:
                refusal_reason = "missed"
                text = templates.REFUSAL_MISSED

        if not refusal_reason:
            continue

        # Уже обрабатывали?
        if await was_sent(course_id, f"refusal_{refusal_reason}"):
            continue

        # Завершаем курс
        await course_service.set_refused(course_id)

        # Записываем в intake_logs
        await intake_logs_service.create(
            course_id=course_id,
            day=current_day,
            status="missed",
            video_file_id="",
        )

        await mark_sent(course_id, f"refusal_{refusal_reason}")

        # Отправляем сообщение
        telegram_id = await user_service.get_telegram_id(course["user_id"])
        if telegram_id:
            try:
                await bot.send_message(chat_id=telegram_id, text=text)
                print(f"🚫 Refusal ({refusal_reason}) → {telegram_id}")
                any_refusal = True
            except Exception as e:
                print(f"❌ Refusal failed: {e}")

    # Обновляем дашборд если были отказы
    if any_refusal:
        await dashboard_service.update_refusals(bot, settings.general_thread_id)


@broker.task(schedule=[{"cron": "0 3 * * *"}])  # 3:00 ночи каждый день
async def cleanup_expired_links():
    """Удаляет неиспользованные ссылки старше 24 часов."""
    supabase = await get_supabase()

    # 24 часа назад
    now = get_tashkent_now()
    threshold = (now - timedelta(hours=24)).isoformat()

    # Находим просроченные курсы
    result = await supabase.table("courses") \
        .select("id, user_id") \
        .eq("status", "setup") \
        .eq("invite_used", False) \
        .lt("created_at", threshold) \
        .execute()

    deleted_count = 0

    for course in result.data or []:
        course_id = course["id"]
        user_id = course["user_id"]

        try:
            # Удаляем course
            await supabase.table("courses").delete().eq("id", course_id).execute()

            # Удаляем user (если нет других курсов)
            other_courses = await supabase.table("courses") \
                .select("id") \
                .eq("user_id", user_id) \
                .execute()

            if not other_courses.data:
                await supabase.table("users").delete().eq("id", user_id).execute()

            deleted_count += 1
        except Exception as e:
            print(f"❌ Cleanup failed for course {course_id}: {e}")

    if deleted_count:
        print(f"🧹 Cleaned up {deleted_count} expired links")



@broker.task(schedule=[{"cron": "* * * * *"}])
async def refresh_active_dashboard():
    """Обновляет дашборд активных курсов."""

    settings = get_settings()
    supabase = await get_supabase()

    dashboard_service = DashboardService(
        supabase=supabase,
        group_chat_id=settings.manager_group_id,
    )
    stats_service = StatsMessagesService(supabase)

    active_text = await dashboard_service.generate_active_courses()
    await _update_or_create_dashboard(
        stats_service=stats_service,
        dashboard_type="active",
        text=active_text,
        chat_id=settings.manager_group_id,
        thread_id=settings.general_thread_id,
    )


async def _update_or_create_dashboard(
        stats_service: StatsMessagesService,
        dashboard_type: str,
        text: str,
        chat_id: int,
        thread_id: int,
) -> None:
    """Обновляет существующее сообщение или создаёт новое."""

    existing = await stats_service.get_by_type(dashboard_type)

    if existing and existing.get("message_id"):
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=existing["message_id"],
                text=text,
                parse_mode="HTML",
            )
            await stats_service.update_timestamp(dashboard_type)
            print(f"📊 Dashboard '{dashboard_type}' updated")
            return
        except Exception as e:
            error_msg = str(e).lower()

            # Текст не изменился — это нормально
            if "message is not modified" in error_msg:
                print(f"📊 Dashboard '{dashboard_type}' unchanged")
                return

            # Сообщение удалено — создаём новое
            if "message to edit not found" in error_msg:
                print(f"⚠️ Message not found, recreating...")
            else:
                print(f"⚠️ Edit failed: {e}")
                return

    # Создаём новое сообщение
    try:
        message = await bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text=text,
            parse_mode="HTML",
        )

        try:
            await bot.pin_chat_message(
                chat_id=chat_id,
                message_id=message.message_id,
                disable_notification=True
            )
        except Exception:
            pass

        await stats_service.upsert(
            message_type=dashboard_type,
            message_id=message.message_id,
            chat_id=chat_id,
            thread_id=thread_id,
        )
        print(f"📊 Dashboard '{dashboard_type}' created")
    except Exception as e:
        print(f"❌ Failed to create dashboard: {e}")