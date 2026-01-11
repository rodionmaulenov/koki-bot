"""Запуск бота через Long Polling (без webhook/nginx)."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from rich.logging import RichHandler
from supabase._async.client import create_client as acreate_client

from app.config import get_settings
from app.handlers.group import router as group_router
from app.handlers.private import router as private_router
from app.handlers.video import router as video_router
from app.handlers.fallback import router as fallback_router
from app.services.users import UserService
from app.services.managers import ManagerService
from app.services.courses import CourseService
from app.services.intake_logs import IntakeLogsService
from app.services.topic import TopicService
from app.services.gemini import GeminiService
from app.services.stats_messages import StatsMessagesService
from app.services.commands_messages import CommandsMessagesService
from app.middleware import SaveCommandsMessageMiddleware

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(message)s",
    handlers=[RichHandler(rich_tracebacks=True)]
)

logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def main():
    """Запуск бота."""
    settings = get_settings()

    # Bot & Dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Роутеры
    dp.include_router(group_router)
    dp.include_router(private_router)
    dp.include_router(video_router)
    dp.include_router(fallback_router)

    # База данных
    supabase = await acreate_client(
        settings.supabase_url,
        settings.supabase_key,
    )

    # Сервисы
    dp["user_service"] = UserService(supabase)
    dp["manager_service"] = ManagerService(supabase)
    dp["course_service"] = CourseService(supabase)
    dp["intake_logs_service"] = IntakeLogsService(supabase)
    dp["topic_service"] = TopicService(
        bot=bot,
        group_chat_id=settings.kok_group_id,
    )
    dp["gemini_service"] = GeminiService()
    dp["stats_messages_service"] = StatsMessagesService(supabase, settings.bot_type)
    dp["commands_messages_service"] = CommandsMessagesService(supabase, settings.bot_type)
    dp["settings"] = settings
    dp["bot"] = bot
    dp["supabase"] = supabase

    # Middleware для сохранения message_id в топике Команды
    dp.message.middleware(SaveCommandsMessageMiddleware())

    logger.info("🚀 Бот запускается (polling)...")

    try:
        # Удаляем webhook если был
        await bot.delete_webhook(drop_pending_updates=True)

        # Запускаем polling
        await dp.start_polling(bot)
    finally:
        logger.info("🛑 Бот остановлен")
        await supabase.auth.sign_out()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())