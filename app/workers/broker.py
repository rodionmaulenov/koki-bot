"""Настройка Taskiq брокера."""

import logging

from redis.asyncio import from_url
from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

broker = ListQueueBroker(url=settings.redis_url)

_redis = None


async def get_redis():
    """Возвращает async Redis клиент."""
    global _redis
    if _redis is None:
        _redis = from_url(settings.redis_url)
    return _redis


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup(state: TaskiqState):
    """Выполняется при старте worker'а."""
    from app.workers.database import get_supabase

    state.supabase = await get_supabase()
    state.redis = await get_redis()
    logger.info("Supabase connected")
    logger.info("Redis connected")


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown(state: TaskiqState):
    """Выполняется при остановке worker'а."""
    from app.workers.bot import bot

    if hasattr(state, "supabase") and state.supabase:
        await state.supabase.auth.sign_out()
        logger.info("Supabase disconnected")

    if hasattr(state, "redis") and state.redis:
        await state.redis.close()
        logger.info("Redis disconnected")

    await bot.session.close()
    logger.info("Bot session closed")


# Импортируем задачи чтобы они зарегистрировались
from app.workers import tasks  # noqa: E402, F401