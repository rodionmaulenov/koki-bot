"""Shared fixtures for handler integration tests (MockTelegramBot + Dishka)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.aiogram import setup_dishka
from redis.asyncio import Redis

from config import Settings
from handlers.add import router as add_router
from handlers.menu import router as menu_router
from handlers.onboarding import router as onboarding_router
from handlers.payment import router as payment_router
from handlers.reissue import router as reissue_router
from handlers.video import router as video_router
from repositories.commands_messages_repository import CommandsMessagesRepository
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.owner_repository import OwnerRepository
from repositories.payment_receipt_repository import PaymentReceiptRepository
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
COMMANDS_THREAD_ID = 42


# ── Mock holder ──────────────────────────────────────────────────────────────


class MockHolder:
    """Holds all mock dependencies, accessible by tests for setup/assertions."""

    def __init__(self) -> None:
        self.settings = MagicMock(spec=Settings)
        self.settings.kok_group_id = KOK_GROUP_ID
        self.settings.kok_general_topic_id = KOK_GENERAL_TOPIC_ID
        self.settings.bot_type = "kok_test"
        self.settings.commands_group_id = KOK_GROUP_ID
        self.settings.commands_thread_id = COMMANDS_THREAD_ID

        self.redis = AsyncMock(spec=Redis)
        self.course_repo = AsyncMock(spec=CourseRepository)
        self.user_repo = AsyncMock(spec=UserRepository)
        self.manager_repo = AsyncMock(spec=ManagerRepository)
        self.manager_repo.get_by_telegram_id.return_value = None
        self.manager_repo.get_active_by_role.return_value = []
        self.owner_repo = AsyncMock(spec=OwnerRepository)
        self.intake_log_repo = AsyncMock(spec=IntakeLogRepository)
        self.commands_messages_repo = AsyncMock(spec=CommandsMessagesRepository)
        self.commands_messages_service = AsyncMock(spec=CommandsMessagesService)
        self.add_service = AsyncMock(spec=AddService)
        self.video_service = AsyncMock(spec=VideoService)
        self.gemini_service = AsyncMock(spec=GeminiService)
        self.ocr_service = AsyncMock(spec=OCRService)
        self.payment_receipt_repo = AsyncMock(spec=PaymentReceiptRepository)
        self.tracked_bot = AsyncMock(spec=TrackedBot)


# ── Dishka test provider ─────────────────────────────────────────────────────


class TestProvider(Provider):
    """Dishka provider that returns mocks from MockHolder."""

    scope = Scope.APP

    def __init__(self, mocks: MockHolder) -> None:
        super().__init__()
        self._m = mocks

    @provide
    def settings(self) -> Settings:
        return self._m.settings

    @provide
    def redis(self) -> Redis:
        return self._m.redis

    @provide
    def course_repo(self) -> CourseRepository:
        return self._m.course_repo

    @provide
    def user_repo(self) -> UserRepository:
        return self._m.user_repo

    @provide
    def manager_repo(self) -> ManagerRepository:
        return self._m.manager_repo

    @provide
    def owner_repo(self) -> OwnerRepository:
        return self._m.owner_repo

    @provide
    def intake_log_repo(self) -> IntakeLogRepository:
        return self._m.intake_log_repo

    @provide
    def commands_messages_repo(self) -> CommandsMessagesRepository:
        return self._m.commands_messages_repo

    @provide
    def commands_messages_service(self) -> CommandsMessagesService:
        return self._m.commands_messages_service

    @provide
    def add_service(self) -> AddService:
        return self._m.add_service

    @provide
    def video_service(self) -> VideoService:
        return self._m.video_service

    @provide
    def gemini_service(self) -> GeminiService:
        return self._m.gemini_service

    @provide
    def ocr_service(self) -> OCRService:
        return self._m.ocr_service

    @provide
    def payment_receipt_repo(self) -> PaymentReceiptRepository:
        return self._m.payment_receipt_repo

    @provide
    def tracked_bot(self) -> TrackedBot:
        return self._m.tracked_bot


# ── Dispatcher factory ───────────────────────────────────────────────────────


_TOP_ROUTERS = [onboarding_router, payment_router, video_router, add_router, reissue_router, menu_router]


async def create_test_dispatcher(mocks: MockHolder) -> Dispatcher:
    """Create Dispatcher with routers and Dishka container (mock deps).

    Router order matches main.py. No access-control middlewares —
    those are tested separately in topic_access/.

    Routers are module-level singletons in aiogram, so we detach them
    from any previous Dispatcher before re-attaching.
    """
    dp = Dispatcher(storage=MemoryStorage())

    # Detach routers from previous Dispatcher (safe: old dp is GC'd)
    for r in _TOP_ROUTERS:
        r._parent_router = None

    # Same order as main.py
    for r in _TOP_ROUTERS:
        dp.include_router(r)

    container = make_async_container(TestProvider(mocks))
    setup_dishka(container=container, router=dp, auto_inject=True)

    # Trigger startup so auto_inject processes handlers
    await dp.emit_startup()

    return dp


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mocks() -> MockHolder:
    """Fresh MockHolder for each test."""
    return MockHolder()
