import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from redis.asyncio import Redis

from config import Settings
from repositories.course_repository import CourseRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from templates import WorkerTemplates, fallback_manager_name
from utils.telegram_retry import tg_retry
from utils.time import calculate_appeal_deadline, get_tashkent_now
from workers.dedup import mark_sent, was_sent

logger = logging.getLogger(__name__)

REMINDER_TYPE = "appeal_expired"
DEADLINE_KEY_TTL = 86400 * 3  # 3 days

# Topic icon for refused course
TOPIC_ICON_REFUSED = 5379748062124056162  # ❗️


async def run(
    bot: Bot,
    redis: Redis,
    settings: Settings,
    course_repository: CourseRepository,
    user_repository: UserRepository,
    manager_repository: ManagerRepository,
) -> None:
    """Check appeal courses: if deadline passed → auto-refuse."""
    now = get_tashkent_now()

    courses = await course_repository.get_appeal_courses()

    for course in courses:
        if await was_sent(redis, course.id, REMINDER_TYPE):
            continue

        # Get or calculate deadline (stored in Redis on first check)
        deadline_key = f"appeal_deadline:{course.id}"
        stored = await redis.get(deadline_key)

        if not stored:
            deadline = calculate_appeal_deadline(now, course.intake_time)
            await redis.set(deadline_key, deadline.isoformat(), ex=DEADLINE_KEY_TTL)
            logger.info(
                "Appeal deadline set for course_id=%d: %s",
                course.id, deadline.isoformat(),
            )
            continue

        deadline = datetime.fromisoformat(stored)
        if now <= deadline:
            continue

        # Auto-refuse appeal
        new_appeal_count = course.appeal_count + 1
        refused = await course_repository.refuse_if_appeal(course.id, new_appeal_count)
        if not refused:
            await mark_sent(redis, course.id, REMINDER_TYPE)
            await redis.delete(deadline_key)
            continue

        await mark_sent(redis, course.id, REMINDER_TYPE)
        await redis.delete(deadline_key)

        user = await user_repository.get_by_id(course.user_id)
        if not user:
            continue

        manager = await manager_repository.get_by_id(user.manager_id)
        manager_name = manager.name if manager else fallback_manager_name()

        # Notify girl
        if user.telegram_id:
            try:
                await tg_retry(
                    bot.send_message,
                    chat_id=user.telegram_id,
                    text=WorkerTemplates.removal_appeal_expired(manager_name),
                )
            except TelegramForbiddenError:
                logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)
            except Exception:
                logger.exception("Failed to send appeal expired to %d", user.telegram_id)

        # Topic: message + icon + close
        if user.topic_id:
            try:
                await tg_retry(
                    bot.send_message,
                    chat_id=settings.kok_group_id,
                    message_thread_id=user.topic_id,
                    text=WorkerTemplates.topic_appeal_expired(),
                )
            except Exception:
                logger.warning("Failed to send appeal expired to topic_id=%d", user.topic_id)

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
            "text": WorkerTemplates.general_appeal_expired(
                manager_name, user.name, user.topic_id, settings.kok_group_id,
            ),
        }
        if settings.kok_general_topic_id:
            kwargs["message_thread_id"] = settings.kok_general_topic_id
        try:
            await tg_retry(bot.send_message, **kwargs)
        except Exception:
            logger.warning("Failed to send appeal expired to general topic")

        logger.info(
            "Appeal auto-refused: course_id=%d, appeal_count=%d",
            course.id, new_appeal_count,
        )
