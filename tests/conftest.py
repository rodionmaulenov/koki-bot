"""Общие fixtures для тестов."""
import random
import secrets
from pathlib import Path

import pytest
import pytest_asyncio
from datetime import date, timedelta, datetime
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import User, Chat, Message, CallbackQuery
from dotenv import load_dotenv

# =============================================================================
# ЗАГРУЗКА ТЕСТОВОГО ОКРУЖЕНИЯ
# =============================================================================

# Загружаем .env.test ПЕРЕД импортом настроек
env_test_path = Path(__file__).parent.parent / ".env.test"
if env_test_path.exists():
    load_dotenv(env_test_path, override=True)
else:
    raise FileNotFoundError(
        f"Файл .env.test не найден: {env_test_path}\n"
        "Создайте .env.test с тестовыми credentials Supabase."
    )

# Теперь импортируем настройки (они загрузят переменные из .env.test)
from supabase._async.client import create_client as acreate_client

from app.config import get_settings
from app.services.users import UserService
from app.services.managers import ManagerService
from app.services.courses import CourseService
from app.services.topic import TopicService
from app.services.intake_logs import IntakeLogsService
from app.utils.time_utils import get_tashkent_now


# =============================================================================
# DATABASE (ТЕСТОВАЯ)
# =============================================================================

@pytest_asyncio.fixture
async def supabase():
    """Создаёт подключение к ТЕСТОВОЙ Supabase."""
    settings = get_settings()
    client = await acreate_client(settings.supabase_url, settings.supabase_key)
    yield client
    await client.auth.sign_out()


# =============================================================================
# SERVICES
# =============================================================================

@pytest_asyncio.fixture
async def user_service(supabase):
    """UserService с тестовой БД."""
    return UserService(supabase)


@pytest_asyncio.fixture
async def manager_service(supabase):
    """ManagerService с тестовой БД."""
    return ManagerService(supabase)


@pytest_asyncio.fixture
async def course_service(supabase):
    """CourseService с тестовой БД."""
    return CourseService(supabase)


@pytest_asyncio.fixture
async def topic_service(mock_bot):
    """TopicService с mock ботом."""
    settings = get_settings()
    return TopicService(bot=mock_bot, group_chat_id=settings.manager_group_id)


@pytest_asyncio.fixture
async def intake_logs_service(supabase):
    """IntakeLogsService с тестовой БД."""
    return IntakeLogsService(supabase)


# =============================================================================
# CLEANUP HELPERS
# =============================================================================

async def cleanup_course(supabase, course_id: int) -> None:
    """Удаляет курс и связанные intake_logs."""
    await supabase.table("intake_logs").delete().eq("course_id", course_id).execute()
    await supabase.table("reminders_sent").delete().eq("course_id", course_id).execute()
    await supabase.table("courses").delete().eq("id", course_id).execute()


async def cleanup_user(supabase, user_id: int) -> None:
    """Удаляет user и все связанные данные."""
    # Сначала находим все курсы пользователя
    courses = await supabase.table("courses").select("id").eq("user_id", user_id).execute()

    # Удаляем intake_logs, reminders_sent и courses
    for course in courses.data or []:
        await cleanup_course(supabase, course["id"])

    # Удаляем пользователя
    await supabase.table("users").delete().eq("id", user_id).execute()


async def cleanup_manager(supabase, manager_id: int) -> None:
    """Удаляет менеджера и всех связанных users."""
    # Находим всех users менеджера
    users = await supabase.table("users").select("id").eq("manager_id", manager_id).execute()

    # Удаляем каждого user (вместе с courses и intake_logs)
    for user in users.data or []:
        await cleanup_user(supabase, user["id"])

    # Удаляем менеджера
    await supabase.table("managers").delete().eq("id", manager_id).execute()


# =============================================================================
# TIME HELPERS
# =============================================================================

def get_current_intake_time() -> str:
    """Возвращает intake_time = текущее время (для тестов в окне)."""
    now = get_tashkent_now()
    return f"{now.hour:02d}:{now.minute:02d}"


def get_intake_time_in_window() -> str:
    """Возвращает intake_time так, чтобы сейчас было в окне приёма.

    Окно: intake_time - 10 мин до intake_time + 2 часа.
    Возвращаем intake_time = now - 5 минут (гарантированно в окне).
    """
    now = get_tashkent_now()
    # 5 минут назад — гарантированно в окне (10 мин до, 2 часа после)
    minutes = now.hour * 60 + now.minute - 5
    if minutes < 0:
        minutes += 24 * 60
    hour = minutes // 60
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


def get_intake_time_too_early() -> str:
    """Возвращает intake_time так, чтобы сейчас было слишком рано.

    Окно начинается за 10 минут до intake_time.
    Возвращаем intake_time = now + 30 минут (сейчас за 30 мин до окна).
    """
    now = get_tashkent_now()
    minutes = now.hour * 60 + now.minute + 30
    hour = (minutes // 60) % 24
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


# =============================================================================
# TEST DATA
# =============================================================================

@pytest_asyncio.fixture
async def test_manager(supabase):
    """Создаёт тестового менеджера."""
    telegram_id = random.randint(700000000, 799999999)

    result = await supabase.table("managers").insert({
        "telegram_id": telegram_id,
        "name": "Test Manager",
        "is_active": True,
    }).execute()

    manager = result.data[0]
    yield manager

    # Cleanup: удаляем менеджера и все связанные данные
    await cleanup_manager(supabase, manager["id"])


@pytest_asyncio.fixture
async def test_user(supabase, test_manager):
    """Создаёт тестового пользователя без telegram_id."""
    result = await supabase.table("users").insert({
        "name": "Тест Девушка",
        "manager_id": test_manager["id"],
        "telegram_id": None,
    }).execute()

    user = result.data[0]
    yield user

    # Cleanup происходит в test_manager


@pytest_asyncio.fixture
async def test_user_with_telegram(supabase, test_manager):
    """Создаёт тестового пользователя с telegram_id."""
    telegram_id = random.randint(800000000, 899999999)

    result = await supabase.table("users").insert({
        "name": "Тест Девушка",
        "manager_id": test_manager["id"],
        "telegram_id": telegram_id,
    }).execute()

    user = result.data[0]
    yield user

    # Cleanup происходит в test_manager


@pytest_asyncio.fixture
async def test_course(supabase, test_user):
    """Создаёт тестовый курс в статусе setup."""
    invite_code = secrets.token_urlsafe(8)

    result = await supabase.table("courses").insert({
        "user_id": test_user["id"],
        "invite_code": invite_code,
        "status": "setup",
    }).execute()

    course = result.data[0]
    yield course

    # Cleanup происходит в test_manager через test_user


@pytest_asyncio.fixture
async def test_active_course(supabase, test_user_with_telegram):
    """Создаёт активный курс с динамическим intake_time (в окне приёма)."""
    invite_code = secrets.token_urlsafe(8)
    start_date = (date.today() - timedelta(days=4)).isoformat()
    intake_time = get_intake_time_in_window()

    result = await supabase.table("courses").insert({
        "user_id": test_user_with_telegram["id"],
        "invite_code": invite_code,
        "invite_used": True,
        "status": "active",
        "cycle_day": 1,
        "intake_time": intake_time,
        "start_date": start_date,
        "current_day": 5,
        "late_count": 0,
    }).execute()

    course = result.data[0]
    yield course

    # Cleanup происходит в test_manager через test_user_with_telegram


@pytest_asyncio.fixture
async def test_active_course_too_early(supabase, test_user_with_telegram):
    """Создаёт активный курс с intake_time в будущем (слишком рано)."""
    invite_code = secrets.token_urlsafe(8)
    start_date = (date.today() - timedelta(days=4)).isoformat()
    intake_time = get_intake_time_too_early()

    result = await supabase.table("courses").insert({
        "user_id": test_user_with_telegram["id"],
        "invite_code": invite_code,
        "invite_used": True,
        "status": "active",
        "cycle_day": 1,
        "intake_time": intake_time,
        "start_date": start_date,
        "current_day": 5,
        "late_count": 0,
    }).execute()

    course = result.data[0]
    yield course

    # Cleanup происходит в test_manager через test_user_with_telegram


@pytest_asyncio.fixture
async def test_future_course(supabase, test_user_with_telegram):
    """Создаёт курс который начнётся завтра."""
    tomorrow = (get_tashkent_now().date() + timedelta(days=1)).isoformat()
    invite_code = secrets.token_urlsafe(8)

    result = await supabase.table("courses").insert({
        "user_id": test_user_with_telegram["id"],
        "invite_code": invite_code,
        "status": "active",
        "start_date": tomorrow,
        "current_day": 1,
        "intake_time": "12:00",
    }).execute()

    course = result.data[0]
    yield course

    # Cleanup происходит в test_manager через test_user_with_telegram


# =============================================================================
# FAKE AIOGRAM OBJECTS
# =============================================================================

@pytest.fixture
def fake_user():
    """Фабрика для создания fake User."""

    def _create(
            user_id: int = 123456789,
            first_name: str = "Test",
            username: str = "test_user",
    ):
        return User(
            id=user_id,
            is_bot=False,
            first_name=first_name,
            username=username,
        )

    return _create


@pytest.fixture
def fake_chat():
    """Фабрика для создания fake Chat."""

    def _create(
            chat_id: int = 123456789,
            chat_type: str = "private",
    ):
        return Chat(
            id=chat_id,
            type=chat_type,
        )

    return _create


@pytest.fixture
def mock_message(fake_user, fake_chat):
    """Фабрика для создания mock Message с мокнутыми методами."""

    def _create(
            text: str = "test",
            user_id: int = 123456789,
            chat_id: int = None,
            message_id: int = 1,
    ):
        chat_id = chat_id or user_id

        message = MagicMock(spec=Message)
        message.message_id = message_id
        message.date = datetime.now()
        message.chat = fake_chat(chat_id=chat_id)
        message.from_user = fake_user(user_id=user_id)
        message.text = text
        message.answer = AsyncMock()
        message.reply = AsyncMock()
        message.delete = AsyncMock()
        message.edit_text = AsyncMock()
        message.edit_reply_markup = AsyncMock()

        return message

    return _create


@pytest.fixture
def mock_callback(fake_user, mock_message):
    """Фабрика для создания mock CallbackQuery."""

    def _create(
            data: str = "test",
            user_id: int = 123456789,
            message_text: str = "test message",
    ):
        callback = MagicMock(spec=CallbackQuery)
        callback.id = "test_callback_id"
        callback.from_user = fake_user(user_id=user_id)
        callback.chat_instance = "test_instance"
        callback.data = data
        callback.message = mock_message(user_id=user_id, text=message_text)
        callback.answer = AsyncMock()

        return callback

    return _create


# =============================================================================
# MOCK GEMINI
# =============================================================================

@pytest.fixture
def mock_gemini_confirmed():
    """GeminiService который всегда подтверждает видео."""
    gemini = MagicMock()
    gemini.verify_video = AsyncMock(return_value={
        "is_taking_pill": True,
        "confidence": 85,
        "reason": "Чётко видно приём таблетки",
        "status": "confirmed",
    })
    gemini.download_video = MagicMock()
    return gemini


@pytest.fixture
def mock_gemini_pending():
    """GeminiService который отправляет на проверку."""
    gemini = MagicMock()
    gemini.verify_video = AsyncMock(return_value={
        "is_taking_pill": False,
        "confidence": 45,
        "reason": "Не видно таблетку",
        "status": "pending",
    })
    gemini.download_video = MagicMock()
    return gemini


# =============================================================================
# MOCK VIDEO MESSAGE
# =============================================================================

@pytest.fixture
def mock_video_message(fake_user, fake_chat):
    """Фабрика для создания mock Message с video_note."""

    def _create(
        user_id: int = 123456789,
        file_id: str = "test_video_file_id",
    ):
        message = MagicMock(spec=Message)
        message.message_id = 1
        message.date = datetime.now()
        message.chat = fake_chat(chat_id=user_id, chat_type="private")
        message.from_user = fake_user(user_id=user_id)
        message.answer = AsyncMock()

        # video_note
        video_note = MagicMock()
        video_note.file_id = file_id
        message.video_note = video_note
        message.video = None

        return message

    return _create


@pytest.fixture
def mock_regular_video_message(fake_user, fake_chat):
    """Фабрика для создания mock Message с обычным video."""

    def _create(
        user_id: int = 123456789,
        file_id: str = "test_video_file_id",
    ):
        message = MagicMock(spec=Message)
        message.message_id = 1
        message.date = datetime.now()
        message.chat = fake_chat(chat_id=user_id, chat_type="private")
        message.from_user = fake_user(user_id=user_id)
        message.answer = AsyncMock()

        # regular video
        video = MagicMock()
        video.file_id = file_id
        message.video = video
        message.video_note = None

        return message

    return _create


# =============================================================================
# BOT (MOCK)
# =============================================================================

@pytest.fixture
def bot():
    """Mock бота для всех тестов (не делает реальных API вызовов)."""
    mock = MagicMock()
    mock.send_message = AsyncMock(return_value=MagicMock(message_id=123))
    mock.edit_message_text = AsyncMock()
    mock.edit_forum_topic = AsyncMock()
    mock.create_forum_topic = AsyncMock(return_value=MagicMock(message_thread_id=456))
    mock.delete_message = AsyncMock()
    mock.pin_chat_message = AsyncMock()
    mock.send_video_note = AsyncMock()
    mock.get_file = AsyncMock()
    mock.download_file = AsyncMock()
    mock.session = MagicMock()
    mock.session.close = AsyncMock()
    return mock


# Алиас для обратной совместимости
@pytest.fixture
def mock_bot(bot):
    """Алиас для bot fixture."""
    return bot


# =============================================================================
# REDIS (MOCK)
# =============================================================================

@pytest.fixture
def redis():
    """Mock Redis для тестов."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.exists = AsyncMock(return_value=False)
    mock.close = AsyncMock()
    return mock


# Алиас для обратной совместимости
@pytest.fixture
def mock_redis(redis):
    """Алиас для redis fixture."""
    return redis