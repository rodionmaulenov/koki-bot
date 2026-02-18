"""Shared fixtures for scenario (end-to-end) tests.

Scenario tests use REAL services + REAL database + MockTelegramBot.
Only GeminiService is mocked (no real AI API calls).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.aiogram import setup_dishka
from redis.asyncio import Redis
from supabase import AsyncClient

from config import Settings
from handlers.add import router as add_router
from handlers.menu import router as menu_router
from handlers.onboarding import router as onboarding_router
from handlers.reissue import router as reissue_router
from handlers.video import router as video_router
from repositories.commands_messages_repository import CommandsMessagesRepository
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.owner_repository import OwnerRepository
from repositories.user_repository import UserRepository
from services.add_service import AddService
from services.gemini_service import GeminiService
from services.ocr_service import OCRService
from services.video_service import VideoService
from topic_access.service import CommandsMessagesService
from topic_access.tracked_bot import TrackedBot


# ── Constants ────────────────────────────────────────────────────────────────

KOK_GROUP_ID = -1009999999999
KOK_GENERAL_TOPIC_ID = 100


# ── Scenario Provider ────────────────────────────────────────────────────────


class ScenarioProvider(Provider):
    """Dishka provider: real services backed by DB + mock GeminiService.

    Real: Settings, all repositories, VideoService
    Mock: GeminiService, Redis, AddService, OCRService, TrackedBot
    """

    scope = Scope.APP

    def __init__(
        self,
        supabase: AsyncClient,
        gemini_mock: GeminiService,
    ) -> None:
        super().__init__()
        self._supabase = supabase
        self._gemini_mock = gemini_mock

    @provide
    def settings(self) -> Settings:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.kok_group_id = KOK_GROUP_ID
        mock_settings.kok_general_topic_id = KOK_GENERAL_TOPIC_ID
        mock_settings.bot_type = "kok_test"
        return mock_settings

    @provide
    def redis(self) -> Redis:
        return AsyncMock(spec=Redis)

    # ── Real repositories (backed by Supabase) ──

    @provide
    def course_repo(self) -> CourseRepository:
        return CourseRepository(self._supabase)

    @provide
    def user_repo(self) -> UserRepository:
        return UserRepository(self._supabase)

    @provide
    def manager_repo(self) -> ManagerRepository:
        return ManagerRepository(self._supabase)

    @provide
    def intake_log_repo(self) -> IntakeLogRepository:
        return IntakeLogRepository(self._supabase)

    @provide
    def owner_repo(self) -> OwnerRepository:
        return OwnerRepository(self._supabase)

    # ── Real services (use real repos) ──

    @provide
    def video_service(
        self,
        course_repo: CourseRepository,
        intake_log_repo: IntakeLogRepository,
    ) -> VideoService:
        return VideoService(course_repo, intake_log_repo)

    # ── Mocked services ──

    @provide
    def gemini_service(self) -> GeminiService:
        return self._gemini_mock

    @provide
    def commands_messages_repo(self) -> CommandsMessagesRepository:
        return AsyncMock(spec=CommandsMessagesRepository)

    @provide
    def commands_messages_service(self) -> CommandsMessagesService:
        return AsyncMock(spec=CommandsMessagesService)

    @provide
    def add_service(self) -> AddService:
        return AsyncMock(spec=AddService)

    @provide
    def ocr_service(self) -> OCRService:
        return AsyncMock(spec=OCRService)

    @provide
    def tracked_bot(self) -> TrackedBot:
        return AsyncMock(spec=TrackedBot)


# ── Dispatcher factory ───────────────────────────────────────────────────────

_TOP_ROUTERS = [onboarding_router, video_router, add_router, reissue_router, menu_router]


async def create_scenario_dispatcher(
    supabase: AsyncClient,
    gemini_mock: GeminiService,
) -> Dispatcher:
    """Create Dispatcher with real services backed by Supabase.

    Settings is a MagicMock with test constants (kok_group_id, etc.).
    Same router order as main.py. No access-control middlewares.
    """
    dp = Dispatcher(storage=MemoryStorage())

    # Detach routers from previous Dispatcher (aiogram singletons)
    for r in _TOP_ROUTERS:
        r._parent_router = None

    for r in _TOP_ROUTERS:
        dp.include_router(r)

    container = make_async_container(
        ScenarioProvider(supabase, gemini_mock),
    )
    setup_dishka(container=container, router=dp, auto_inject=True)

    await dp.emit_startup()
    return dp


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def auto_cleanup_db(cleanup_db):
    """Automatically clean database before/after each scenario test."""
    yield