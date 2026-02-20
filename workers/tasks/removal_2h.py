import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from redis.asyncio import Redis

from config import Settings
from keyboards.appeal import appeal_button
from models.enums import RemovalReason
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from templates import AppealTemplates, WorkerTemplates, fallback_manager_name
from utils.telegram_retry import tg_retry
from utils.time import calculate_time_range_after, get_tashkent_now
from workers.dedup import mark_sent, was_sent

logger = logging.getLogger(__name__)

REMINDER_TYPE = "removal_2h"

# Topic icon for refused course
TOPIC_ICON_REFUSED = 5379748062124056162  # ❗️


async def run(
    bot: Bot,
    redis: Redis,
    settings: Settings,
    course_repository: CourseRepository,
    user_repository: UserRepository,
    manager_repository: ManagerRepository,
    intake_log_repository: IntakeLogRepository,
) -> None:
    """Check +2 hours after intake: no video → auto-removal."""
    now = get_tashkent_now()
    today = now.date().isoformat()
    time_from, time_to = calculate_time_range_after(120)

    courses = await course_repository.get_active_in_intake_window(
        today, time_from.isoformat(), time_to.isoformat(),
    )

    for course in courses:
        if await was_sent(redis, course.id, REMINDER_TYPE):
            continue

        # Check if video already sent for this intake date
        intake_date = (now - timedelta(minutes=120)).date()
        expected_day = (intake_date - course.start_date).days + 1
        has_log = await intake_log_repository.has_log_today(course.id, expected_day)
        if has_log:
            continue

        # Refuse course (atomic: only if still active)
        refused = await course_repository.refuse_if_active(course.id, removal_reason=RemovalReason.NO_VIDEO)
        if not refused:
            await mark_sent(redis, course.id, REMINDER_TYPE)
            continue

        await mark_sent(redis, course.id, REMINDER_TYPE)

        user = await user_repository.get_by_id(course.user_id)
        if not user:
            continue

        manager = await manager_repository.get_by_id(user.manager_id)
        manager_name = manager.name if manager else fallback_manager_name()

        # Notify girl (with appeal button if eligible)
        if user.telegram_id:
            markup = appeal_button(course.id) if course.appeal_count < AppealTemplates.MAX_APPEALS else None
            try:
                await tg_retry(
                    bot.send_message,
                    chat_id=user.telegram_id,
                    text=WorkerTemplates.removal_no_video(manager_name),
                    reply_markup=markup,
                )
            except TelegramForbiddenError:
                logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)
            except Exception:
                logger.exception("Failed to send removal to %d", user.telegram_id)

        # Topic: message + icon + close
        if user.topic_id:
            try:
                await tg_retry(
                    bot.send_message,
                    chat_id=settings.kok_group_id,
                    message_thread_id=user.topic_id,
                    text=WorkerTemplates.topic_removal_no_video(),
                )
            except Exception:
                logger.warning("Failed to send removal to topic_id=%d", user.topic_id)

            try:
                await tg_retry(
                    bot.edit_forum_topic,
                    chat_id=settings.kok_group_id,
                    message_thread_id=user.topic_id,
                    icon_custom_emoji_id=str(TOPIC_ICON_REFUSED),
                )
            except Exception:
                logger.warning("Failed to change icon for topic_id=%d", user.topic_id)

            try:
                await tg_retry(
                    bot.close_forum_topic,
                    chat_id=settings.kok_group_id,
                    message_thread_id=user.topic_id,
                )
            except Exception:
                logger.warning("Failed to close topic_id=%d", user.topic_id)

        # General topic
        kwargs: dict[str, object] = {
            "chat_id": settings.kok_group_id,
            "text": WorkerTemplates.general_removal_no_video(
                user.name, user.topic_id, settings.kok_group_id,
            ),
        }
        if settings.kok_general_topic_id:
            kwargs["message_thread_id"] = settings.kok_general_topic_id
        try:
            await tg_retry(bot.send_message, **kwargs)
        except Exception:
            logger.warning("Failed to send removal to general topic")

        logger.info("Auto-removal (2h): course_id=%d", course.id)
