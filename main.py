import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / (".env.test" if os.getenv("ENV") == "test" else ".env"))

import sentry_sdk
from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka
from redis.asyncio import Redis
from rich.logging import RichHandler
from supabase import AsyncClient

from config import Settings, get_settings
from di.provider import AppProvider
from services.dev_mode_service import DevModeService
from templates import BotDescriptionTemplates
from utils.telegram_error_handler import setup_telegram_error_handler
from workers.scheduler import start_scheduler
from handlers.add import router as add_router
from handlers.menu import ensure_menu, router as menu_router
from handlers.onboarding import router as onboarding_router
from handlers.reissue import router as reissue_router
from handlers.video import router as video_router
from repositories.commands_messages_repository import CommandsMessagesRepository
from repositories.manager_repository import ManagerRepository
from repositories.owner_repository import OwnerRepository
from topic_access.callback_middleware import CallbackMiddleware
from topic_access.message_middleware import MessageMiddleware
from topic_access.tracked_bot import TrackedBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

FSM_TTL = 86400  # 24 hours


async def main() -> None:
    settings = get_settings()

    # Sentry error tracking (optional)
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            send_default_pii=True,
        )
        logger.info("Sentry initialized")

    container = make_async_container(AppProvider(settings))

    redis = await container.get(Redis)
    bot = await container.get(TrackedBot)
    commands_messages_repository = await container.get(CommandsMessagesRepository)
    manager_repository = await container.get(ManagerRepository)
    owner_repository = await container.get(OwnerRepository)

    # Telegram error notifications (optional)
    if settings.error_topic_chat_id and settings.error_topic_id:
        setup_telegram_error_handler(
            bot=bot,
            chat_id=settings.error_topic_chat_id,
            topic_id=settings.error_topic_id,
        )
        logger.info("Telegram error handler initialized")

    storage = RedisStorage(redis, state_ttl=FSM_TTL)
    dp = Dispatcher(storage=storage)

    dp.include_router(onboarding_router)
    dp.include_router(video_router)
    dp.include_router(add_router)
    dp.include_router(reissue_router)
    dp.include_router(menu_router)

    setup_dishka(container=container, router=dp, auto_inject=True)

    _setup_middlewares(
        dp, settings, commands_messages_repository,
        manager_repository, owner_repository, redis,
    )

    # Dev mode: cleanup and seed database
    supabase = await container.get(AsyncClient)
    dev_mode_service = DevModeService(
        supabase=supabase,
        redis=redis,
        settings=settings,
        bot=bot,
    )
    await dev_mode_service.startup()

    logger.info("Starting bot...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await _setup_bot_info(bot)

        await ensure_menu(
            bot=bot,
            chat_id=settings.commands_group_id,
            thread_id=settings.commands_thread_id,
            repository=commands_messages_repository,
        )

        # Start worker scheduler in background
        scheduler_task = asyncio.create_task(
            start_scheduler(bot=bot, redis=redis, supabase=supabase, settings=settings),
        )
        scheduler_task.add_done_callback(_on_scheduler_done)

        await dp.start_polling(bot)
    finally:
        # Cancel scheduler
        if "scheduler_task" in locals():
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        # Dev mode: cleanup on shutdown
        try:
            await dev_mode_service.shutdown()
        except Exception:
            logger.exception("Dev mode shutdown failed")

        logger.info("Shutting down...")
        await container.close()


def _on_scheduler_done(task: asyncio.Task) -> None:
    """Log scheduler failures so they reach TelegramErrorHandler."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Scheduler task crashed: %s", exc, exc_info=exc)


async def _setup_bot_info(bot: TrackedBot) -> None:
    try:
        await bot.set_my_description(
            description=BotDescriptionTemplates.full_description(),
        )
        await bot.set_my_short_description(
            short_description=BotDescriptionTemplates.short_description(),
        )
        await bot.delete_my_commands()
        logger.info("Bot info configured")
    except Exception:
        logger.warning("Failed to setup bot info (rate limit?), skipping")


def _setup_middlewares(
    dp: Dispatcher,
    settings: Settings,
    commands_messages_repository: CommandsMessagesRepository,
    manager_repository: ManagerRepository,
    owner_repository: OwnerRepository,
    redis: Redis,
) -> None:
    message_mw = MessageMiddleware(
        thread_id=settings.commands_thread_id,
        repository=commands_messages_repository,
        manager_repository=manager_repository,
        owner_repository=owner_repository,
        redis=redis,
    )
    callback_mw = CallbackMiddleware(
        thread_id=settings.commands_thread_id,
        manager_repository=manager_repository,
        owner_repository=owner_repository,
    )
    dp.message.outer_middleware(message_mw)
    dp.callback_query.outer_middleware(callback_mw)


if __name__ == "__main__":
    asyncio.run(main())
