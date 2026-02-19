"""
Test configuration and shared fixtures for koki-bot.

Provides fixtures for:
- Settings from .env.test
- Database access (Supabase)
- Redis client
- Repository instances
- Database cleanup
- Test data creation helpers
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

# =============================================================================
# UVLOOP FOR FASTER ASYNC (Linux/macOS only)
# =============================================================================


def _install_uvloop() -> None:
    if sys.platform == "win32":
        return
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass


_install_uvloop()

# =============================================================================
# LOAD TEST ENVIRONMENT (.env.test)
# =============================================================================

env_test_path = Path(__file__).parent.parent / ".env.test"
if env_test_path.exists():
    load_dotenv(env_test_path, override=True)

import pytest
from redis.asyncio import from_url as redis_from_url
from supabase import AsyncClient, acreate_client

from config import Settings, get_settings
from models.course import Course
from models.document import Document
from models.intake_log import IntakeLog
from models.manager import Manager
from models.payment_receipt import PaymentReceipt
from models.user import User
from repositories.commands_messages_repository import CommandsMessagesRepository
from repositories.course_repository import CourseRepository
from repositories.document_repository import DocumentRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.payment_receipt_repository import PaymentReceiptRepository
from repositories.user_repository import UserRepository


# =============================================================================
# BASE FIXTURES
# =============================================================================


@pytest.fixture
def settings() -> Settings:
    """Load settings from .env.test."""
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
async def supabase(settings: Settings) -> AsyncClient:
    """Create async Supabase client."""
    return await acreate_client(settings.supabase_url, settings.supabase_key)


@pytest.fixture
async def redis(settings: Settings):
    """Redis client for tests (DB 2 — separate from prod)."""
    client = redis_from_url(settings.redis_url)
    yield client
    await client.aclose()


# =============================================================================
# CLEANUP
# =============================================================================


async def delete_all(supabase: AsyncClient) -> None:
    """Delete all test data from database."""
    # kok schema (order matters: FK dependencies)
    await supabase.schema("kok").table("payment_receipts").delete().neq("id", 0).execute()
    await supabase.schema("kok").table("intake_logs").delete().neq("id", 0).execute()
    await supabase.schema("kok").table("courses").delete().neq("id", 0).execute()
    await supabase.schema("kok").table("documents").delete().neq("id", 0).execute()
    await supabase.schema("kok").table("users").delete().neq("id", 0).execute()
    # public schema
    await supabase.table("commands_messages").delete().neq("id", 0).execute()
    await supabase.table("managers").delete().neq("id", 0).execute()


@pytest.fixture
async def cleanup_db(supabase: AsyncClient):
    """Clean all test data before and after each test.

    NOT autouse — add to per-directory conftest.py files
    that need database cleanup (repositories, workers).
    """
    await delete_all(supabase)
    yield
    await delete_all(supabase)


# =============================================================================
# REPOSITORY FIXTURES
# =============================================================================


@pytest.fixture
def course_repository(supabase: AsyncClient) -> CourseRepository:
    return CourseRepository(supabase)


@pytest.fixture
def user_repository(supabase: AsyncClient) -> UserRepository:
    return UserRepository(supabase)


@pytest.fixture
def intake_log_repository(supabase: AsyncClient) -> IntakeLogRepository:
    return IntakeLogRepository(supabase)


@pytest.fixture
def manager_repository(supabase: AsyncClient) -> ManagerRepository:
    return ManagerRepository(supabase)


@pytest.fixture
def document_repository(supabase: AsyncClient) -> DocumentRepository:
    return DocumentRepository(supabase)


@pytest.fixture
def payment_receipt_repository(supabase: AsyncClient) -> PaymentReceiptRepository:
    return PaymentReceiptRepository(supabase)


@pytest.fixture
def commands_messages_repository(
    supabase: AsyncClient, settings: Settings,
) -> CommandsMessagesRepository:
    return CommandsMessagesRepository(supabase, bot_type=settings.bot_type)


# =============================================================================
# TEST DATA HELPERS
# =============================================================================


async def create_test_manager(
    supabase: AsyncClient,
    telegram_id: int = 7172139170,
    name: str = "Test Manager",
    is_active: bool = True,
    role: str = "manager",
) -> Manager:
    """Create a test manager in public.managers."""
    response = await (
        supabase.table("managers")
        .insert({"telegram_id": telegram_id, "name": name, "is_active": is_active, "role": role})
        .execute()
    )
    return Manager(**response.data[0])


async def create_test_user(
    supabase: AsyncClient,
    manager_id: int,
    name: str = "Ivanova Marina Alexandrovna",
    telegram_id: int | None = None,
    topic_id: int | None = None,
    birth_date: str | None = None,
) -> User:
    """Create a test user in kok.users."""
    data: dict = {"name": name, "manager_id": manager_id}
    if telegram_id is not None:
        data["telegram_id"] = telegram_id
    if topic_id is not None:
        data["topic_id"] = topic_id
    if birth_date is not None:
        data["birth_date"] = birth_date
    response = await (
        supabase.schema("kok").table("users").insert(data).execute()
    )
    return User(**response.data[0])


async def create_test_course(
    supabase: AsyncClient,
    user_id: int,
    status: str = "setup",
    invite_code: str | None = "TEST12345678",
    invite_used: bool = False,
    intake_time: str | None = None,
    start_date: str | None = None,
    current_day: int = 0,
    total_days: int = 21,
    late_count: int = 0,
    appeal_count: int = 0,
    extended: bool = False,
    late_dates: list[str] | None = None,
) -> Course:
    """Create a test course in kok.courses."""
    data: dict = {
        "user_id": user_id,
        "status": status,
        "invite_used": invite_used,
        "current_day": current_day,
        "total_days": total_days,
        "late_count": late_count,
        "appeal_count": appeal_count,
        "extended": extended,
    }
    if invite_code is not None:
        data["invite_code"] = invite_code
    if intake_time is not None:
        data["intake_time"] = intake_time
    if start_date is not None:
        data["start_date"] = start_date
    if late_dates is not None:
        data["late_dates"] = late_dates
    else:
        data["late_dates"] = []

    response = await (
        supabase.schema("kok").table("courses").insert(data).execute()
    )
    return Course(**response.data[0])


async def create_test_intake_log(
    supabase: AsyncClient,
    course_id: int,
    day: int = 1,
    scheduled_at: str | None = None,
    taken_at: str | None = None,
    status: str = "pending",
    video_file_id: str = "test_video_123",
    delay_minutes: int | None = None,
    verified_by: str | None = None,
    confidence: float | None = None,
    review_started_at: str | None = None,
    reshoot_deadline: str | None = None,
    private_message_id: int | None = None,
) -> IntakeLog:
    """Create a test intake log in kok.intake_logs."""
    data: dict = {
        "course_id": course_id,
        "day": day,
        "status": status,
        "video_file_id": video_file_id,
    }
    if scheduled_at is not None:
        data["scheduled_at"] = scheduled_at
    if taken_at is not None:
        data["taken_at"] = taken_at
    if delay_minutes is not None:
        data["delay_minutes"] = delay_minutes
    if verified_by is not None:
        data["verified_by"] = verified_by
    if confidence is not None:
        data["confidence"] = confidence
    if review_started_at is not None:
        data["review_started_at"] = review_started_at
    if reshoot_deadline is not None:
        data["reshoot_deadline"] = reshoot_deadline
    if private_message_id is not None:
        data["private_message_id"] = private_message_id

    response = await (
        supabase.schema("kok").table("intake_logs").insert(data).execute()
    )
    return IntakeLog(**response.data[0])


async def create_test_document(
    supabase: AsyncClient,
    user_id: int,
    manager_id: int,
    passport_file_id: str | None = "test_passport_file_id",
    receipt_file_id: str | None = "test_receipt_file_id",
    receipt_price: int | None = 150000,
    card_file_id: str | None = "test_card_file_id",
    card_number: str | None = "8600123456789012",
    card_holder_name: str | None = "IVANOVA MARINA",
) -> Document:
    """Create a test document in kok.documents."""
    data: dict = {"user_id": user_id, "manager_id": manager_id}
    if passport_file_id is not None:
        data["passport_file_id"] = passport_file_id
    if receipt_file_id is not None:
        data["receipt_file_id"] = receipt_file_id
    if receipt_price is not None:
        data["receipt_price"] = receipt_price
    if card_file_id is not None:
        data["card_file_id"] = card_file_id
    if card_number is not None:
        data["card_number"] = card_number
    if card_holder_name is not None:
        data["card_holder_name"] = card_holder_name
    response = await (
        supabase.schema("kok").table("documents").insert(data).execute()
    )
    return Document(**response.data[0])


async def create_test_payment_receipt(
    supabase: AsyncClient,
    course_id: int,
    accountant_id: int,
    receipt_file_id: str = "test_payment_receipt_file_id",
    amount: int | None = 150000,
) -> PaymentReceipt:
    """Create a test payment receipt in kok.payment_receipts."""
    data: dict = {
        "course_id": course_id,
        "accountant_id": accountant_id,
        "receipt_file_id": receipt_file_id,
    }
    if amount is not None:
        data["amount"] = amount
    response = await (
        supabase.schema("kok").table("payment_receipts").insert(data).execute()
    )
    return PaymentReceipt(**response.data[0])
