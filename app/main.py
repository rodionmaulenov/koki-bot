import logging

from aiogram.fsm.storage.memory import MemoryStorage
from rich.logging import RichHandler
from contextlib import asynccontextmanager
from supabase._async.client import create_client as acreate_client

from fastapi import FastAPI, Request

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

from app.config import get_settings

from app.handlers.group import router as group_router
from app.handlers.private import router as private_router
from app.handlers.video import router as video_router
from app.handlers.fallback import router as fallback_router

# Services
from app.services.users import UserService
from app.services.managers import ManagerService
from app.services.courses import CourseService
from app.services.intake_logs import IntakeLogsService
from app.services.topic import TopicService
from app.services.gemini import GeminiService


logging.basicConfig(
    level=logging.DEBUG,
    format="%(name)s - %(message)s",
    handlers=[RichHandler(rich_tracebacks=True)]
)

logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
settings = get_settings()

bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

dp.include_router(group_router)
dp.include_router(private_router)
dp.include_router(video_router)
dp.include_router(fallback_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and Shutdown"""
    logger.info("Bot starting...")

    # =========================================================================
    # DATABASE
    # =========================================================================
    supabase = await acreate_client(
        settings.supabase_url,
        settings.supabase_key,
    )

    # =========================================================================
    # SERVICES — сохраняем в dp для доступа из handlers
    # =========================================================================
    dp["user_service"] = UserService(supabase)
    dp["manager_service"] = ManagerService(supabase)
    dp["course_service"] = CourseService(supabase)
    dp["intake_logs_service"] = IntakeLogsService(supabase)
    dp["topic_service"] = TopicService(
        bot=bot,
        group_chat_id=settings.manager_group_id,
    )
    dp["gemini_service"] = GeminiService()
    dp["settings"] = settings
    dp["bot"] = bot
    dp["supabase"] = supabase

    logger.info("Bot commands set")

    logger.info("Supabase connected")
    logger.info("Dispatcher ready")

    yield

    # =========================================================================
    # SHUTDOWN
    # =========================================================================
    logger.info("Bot stopping...")
    await supabase.auth.sign_out()
    await bot.session.close()
    logger.info("Bot stopped")


app = FastAPI(title="Malika Bot", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok", "bot": "Malika"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Принимает все updates от Telegram."""
    data = await request.json()
    logger.debug(f"Received: {data}")

    update = Update(**data)
    await dp.feed_update(bot=bot, update=update)

    return {"ok": True}