import logging
from datetime import timedelta

from aiogram import Bot

from config import Settings
from repositories.course_repository import CourseRepository
from repositories.user_repository import UserRepository
from utils.time import get_tashkent_now

logger = logging.getLogger(__name__)

CLEANUP_AFTER_HOURS = 24


async def run(
    bot: Bot,
    settings: Settings,
    course_repository: CourseRepository,
    user_repository: UserRepository,
) -> None:
    """Delete forum topics for courses that ended 24+ hours ago."""
    cutoff = get_tashkent_now() - timedelta(hours=CLEANUP_AFTER_HOURS)

    users = await user_repository.get_with_topic()
    if not users:
        return

    user_ids = [u.id for u in users]
    ended_user_ids = await course_repository.get_ended_user_ids(user_ids, cutoff)

    for user in users:
        if user.id not in ended_user_ids:
            continue

        try:
            await bot.delete_forum_topic(
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
            )
        except Exception:
            logger.warning("Failed to delete topic %d for user %d", user.topic_id, user.id)

        await user_repository.clear_topic_id(user.id)
        logger.info("Cleaned up topic_id=%d for user_id=%d", user.topic_id, user.id)
