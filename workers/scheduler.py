import asyncio
import logging
from collections.abc import Coroutine

from aiogram import Bot
from redis.asyncio import Redis
from supabase import AsyncClient

from config import Settings
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.video_service import VideoService
from workers.tasks import (
    appeal_button_deadline,
    appeal_deadline,
    reminder_10min,
    reminder_1h,
    removal_2h,
    reshoot_deadline,
    review_deadline,
    strike_30min,
    topic_cleanup,
)

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 300  # 5 minutes


async def start_scheduler(
    bot: Bot,
    redis: Redis,
    supabase: AsyncClient,
    settings: Settings,
) -> None:
    """Start periodic worker loop. Runs every 5 minutes."""
    logger.info("Worker scheduler started (interval=%ds)", INTERVAL_SECONDS)

    while True:
        try:
            await _run_all_tasks(bot, redis, supabase, settings)
        except Exception:
            logger.exception("Worker scheduler tick failed")

        await asyncio.sleep(INTERVAL_SECONDS)


async def _run_all_tasks(
    bot: Bot,
    redis: Redis,
    supabase: AsyncClient,
    settings: Settings,
) -> None:
    """Run all worker tasks once."""
    course_repo = CourseRepository(supabase)
    user_repo = UserRepository(supabase)
    manager_repo = ManagerRepository(supabase)
    intake_log_repo = IntakeLogRepository(supabase)
    video_service = VideoService(course_repo, intake_log_repo)

    # Reminders (before intake)
    await _safe_run("reminder_1h", reminder_1h.run(
        bot=bot, redis=redis,
        course_repository=course_repo, user_repository=user_repo,
    ))

    await _safe_run("reminder_10min", reminder_10min.run(
        bot=bot, redis=redis,
        course_repository=course_repo, user_repository=user_repo,
    ))

    # Strike +30 min
    await _safe_run("strike_30min", strike_30min.run(
        bot=bot, redis=redis, settings=settings,
        course_repository=course_repo, user_repository=user_repo,
        manager_repository=manager_repo,
        intake_log_repository=intake_log_repo,
        video_service=video_service,
    ))

    # Auto-removal +2h
    await _safe_run("removal_2h", removal_2h.run(
        bot=bot, redis=redis, settings=settings,
        course_repository=course_repo, user_repository=user_repo,
        manager_repository=manager_repo,
        intake_log_repository=intake_log_repo,
    ))

    # Review deadline
    await _safe_run("review_deadline", review_deadline.run(
        bot=bot, redis=redis, settings=settings,
        course_repository=course_repo, user_repository=user_repo,
        manager_repository=manager_repo,
        intake_log_repository=intake_log_repo,
    ))

    # Reshoot deadline
    await _safe_run("reshoot_deadline", reshoot_deadline.run(
        bot=bot, redis=redis, settings=settings,
        course_repository=course_repo, user_repository=user_repo,
        manager_repository=manager_repo,
        intake_log_repository=intake_log_repo,
    ))

    # Appeal deadline (manager didn't respond)
    await _safe_run("appeal_deadline", appeal_deadline.run(
        bot=bot, redis=redis, settings=settings,
        course_repository=course_repo, user_repository=user_repo,
        manager_repository=manager_repo,
    ))

    # Appeal button deadline (girl didn't press button in time)
    await _safe_run("appeal_button_deadline", appeal_button_deadline.run(
        bot=bot, redis=redis,
        course_repository=course_repo, user_repository=user_repo,
    ))

    # Topic cleanup (delete topics 24h after course ended)
    await _safe_run("topic_cleanup", topic_cleanup.run(
        bot=bot, settings=settings,
        course_repository=course_repo, user_repository=user_repo,
    ))


async def _safe_run(name: str, coro: Coroutine[object, object, None]) -> None:
    """Run a task with error isolation."""
    try:
        await coro
    except Exception:
        logger.exception("Worker task '%s' failed", name)
