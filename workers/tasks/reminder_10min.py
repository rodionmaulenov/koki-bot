import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from redis.asyncio import Redis

from repositories.course_repository import CourseRepository
from repositories.user_repository import UserRepository
from templates import WorkerTemplates
from utils.telegram_retry import tg_retry
from utils.time import calculate_time_range_before, get_tashkent_now
from workers.dedup import mark_sent, was_sent

logger = logging.getLogger(__name__)

REMINDER_TYPE = "10min"


async def run(
    bot: Bot,
    redis: Redis,
    course_repository: CourseRepository,
    user_repository: UserRepository,
) -> None:
    """Send reminder 10 minutes before intake."""
    now = get_tashkent_now()
    today = now.date().isoformat()
    time_from, time_to = calculate_time_range_before(10)

    courses = await course_repository.get_active_in_intake_window(
        today, time_from.isoformat(), time_to.isoformat(),
    )

    for course in courses:
        if await was_sent(redis, course.id, REMINDER_TYPE):
            continue

        user = await user_repository.get_by_id(course.user_id)
        if not user or not user.telegram_id:
            continue

        intake_str = course.intake_time.strftime("%H:%M") if course.intake_time else ""
        try:
            await tg_retry(
                bot.send_message,
                chat_id=user.telegram_id,
                text=WorkerTemplates.reminder_10min(intake_str),
            )
            await mark_sent(redis, course.id, REMINDER_TYPE)
            logger.info("Reminder 10min → user=%d, course=%d", user.telegram_id, course.id)
        except TelegramForbiddenError:
            logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)
        except Exception:
            logger.exception("Failed to send 10min reminder to %d", user.telegram_id)
