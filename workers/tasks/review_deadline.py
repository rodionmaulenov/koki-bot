import logging
from datetime import datetime, time, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from redis.asyncio import Redis

from config import Settings
from models.enums import RemovalReason
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from templates import WorkerTemplates, fallback_manager_name
from utils.telegram_retry import tg_retry
from utils.time import TASHKENT_TZ, get_tashkent_now
from workers.dedup import mark_sent, was_sent

logger = logging.getLogger(__name__)

REMINDER_TYPE = "review_expired"
DEADLINE_HOURS_BEFORE = 2

# Topic icon for refused course
TOPIC_ICON_REFUSED = 5379748062124056162  # ❗️


def _review_deadline(review_started_at: datetime, intake_time: time) -> datetime:
    """Calculate review deadline: day after review + intake_time - 2h."""
    review_date = review_started_at.date()
    deadline_date = review_date + timedelta(days=1)
    return datetime.combine(deadline_date, intake_time, tzinfo=TASHKENT_TZ) - timedelta(
        hours=DEADLINE_HOURS_BEFORE,
    )


async def run(
    bot: Bot,
    redis: Redis,
    settings: Settings,
    course_repository: CourseRepository,
    user_repository: UserRepository,
    manager_repository: ManagerRepository,
    intake_log_repository: IntakeLogRepository,
) -> None:
    """Check pending_review logs: if deadline passed → auto-removal."""
    now = get_tashkent_now()

    pending_logs = await intake_log_repository.get_pending_reviews_with_start()

    for log in pending_logs:
        if await was_sent(redis, log.course_id, REMINDER_TYPE):
            continue

        course = await course_repository.get_by_id(log.course_id)
        if not course or course.status != "active":
            await mark_sent(redis, log.course_id, REMINDER_TYPE)
            continue

        if not log.review_started_at or not course.intake_time:
            continue

        # Check if deadline has passed
        deadline = _review_deadline(log.review_started_at, course.intake_time)
        if now <= deadline:
            continue

        # Refuse course (atomic: only if still active)
        refused = await course_repository.refuse_if_active(course.id, removal_reason=RemovalReason.REVIEW_DEADLINE)
        if not refused:
            await mark_sent(redis, log.course_id, REMINDER_TYPE)
            continue

        # Mark log as missed
        await intake_log_repository.update_status(log.id, "missed")
        await mark_sent(redis, log.course_id, REMINDER_TYPE)

        user = await user_repository.get_by_id(course.user_id)
        if not user:
            continue

        manager = await manager_repository.get_by_id(user.manager_id)
        manager_name = manager.name if manager else fallback_manager_name()

        # Notify girl (no appeal — manager decision)
        if user.telegram_id:
            try:
                await tg_retry(
                    bot.send_message,
                    chat_id=user.telegram_id,
                    text=WorkerTemplates.removal_review_expired(manager_name),
                )
            except TelegramForbiddenError:
                logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)
            except Exception:
                logger.exception("Failed to send review expired to %d", user.telegram_id)

        # Topic: message + icon + close
        if user.topic_id:
            try:
                await tg_retry(
                    bot.send_message,
                    chat_id=settings.kok_group_id,
                    message_thread_id=user.topic_id,
                    text=WorkerTemplates.topic_removal_review_expired(),
                )
            except Exception:
                logger.warning("Failed to send review expired to topic_id=%d", user.topic_id)

            try:
                await tg_retry(
                    bot.edit_forum_topic,
                    chat_id=settings.kok_group_id,
                    message_thread_id=user.topic_id,
                    icon_custom_emoji_id=str(TOPIC_ICON_REFUSED),
                )
            except Exception:
                logger.error("Failed to change icon for topic_id=%d", user.topic_id)

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
            "text": WorkerTemplates.general_removal_review_expired(
                manager_name, user.name, user.topic_id, settings.kok_group_id,
            ),
        }
        if settings.kok_general_topic_id:
            kwargs["message_thread_id"] = settings.kok_general_topic_id
        try:
            await tg_retry(bot.send_message, **kwargs)
        except Exception:
            logger.warning("Failed to send review expired to general topic")

        logger.info("Review deadline expired: log_id=%d, course_id=%d", log.id, course.id)
