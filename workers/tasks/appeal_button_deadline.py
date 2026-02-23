import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from redis.asyncio import Redis

from repositories.course_repository import CourseRepository
from repositories.user_repository import UserRepository
from templates import WorkerTemplates
from utils.telegram_retry import tg_retry
from utils.time import get_tashkent_now
from workers.dedup import mark_sent, was_sent

logger = logging.getLogger(__name__)

REMINDER_TYPE = "appeal_button_expired"


async def run(
    bot: Bot,
    redis: Redis,
    course_repository: CourseRepository,
    user_repository: UserRepository,
) -> None:
    """Check refused courses with expired appeal_deadline → notify girl."""
    now = get_tashkent_now()

    courses = await course_repository.get_refused_with_expired_appeal(now)

    for course in courses:
        if await was_sent(redis, course.id, REMINDER_TYPE):
            continue

        await mark_sent(redis, course.id, REMINDER_TYPE)

        user = await user_repository.get_by_id(course.user_id)
        if not user or not user.telegram_id:
            continue

        try:
            await tg_retry(
                bot.send_message,
                chat_id=user.telegram_id,
                text=WorkerTemplates.appeal_button_expired(),
            )
        except TelegramForbiddenError:
            logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)
        except Exception:
            logger.exception(
                "Failed to send appeal button expired to %d", user.telegram_id,
            )

        logger.info(
            "Appeal button expired: course_id=%d, user=%d",
            course.id, user.telegram_id,
        )
