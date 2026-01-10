"""Общие fixtures для тестов."""
import random
import secrets
from pathlib import Path
from datetime import date, timedelta, datetime

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import User, Chat, Message, CallbackQuery
from dotenv import load_dotenv

# =============================================================================
# ЗАГРУЗКА ТЕСТОВОГО ОКРУЖЕНИЯ
# =============================================================================

env_test_path = Path(__file__).parent.parent / ".env.test"
if env_test_path.exists():
    load_dotenv(env_test_path, override=True)

# Импортируем после загрузки .env
from app.config import get_settings


# =============================================================================
# TIME HELPERS
# =============================================================================

def get_tashkent_now():
    """Мок текущего времени в Ташкенте."""
    from app.utils.time_utils import get_tashkent_now as real_get_tashkent_now
    return real_get_tashkent_now()


def get_intake_time_in_window() -> str:
    """Возвращает intake_time в окне приёма (5 минут назад).

    Обрабатывает переход через полночь — если вычитание 5 минут
    переводит в предыдущий день, используем фиксированное время.
    """
    now = get_tashkent_now()
    # Если близко к полуночи (первые 15 минут дня), используем фиксированное время
    if now.hour == 0 and now.minute < 15:
        return "00:00"

    minutes = now.hour * 60 + now.minute - 5
    if minutes < 0:
        minutes = 0
    hour = minutes // 60
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


def get_intake_time_too_early() -> str:
    """Возвращает intake_time слишком рано (30 минут в будущем).

    Обрабатывает переход через полночь - если добавление 30 минут
    переводит в следующий день, используем фиксированное время.
    """
    now = get_tashkent_now()
    # Если близко к полуночи (после 23:30), используем фиксированное время
    if now.hour == 23 and now.minute >= 30:
        return "23:59"

    minutes = now.hour * 60 + now.minute + 30
    hour = (minutes // 60) % 24
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


# =============================================================================
# REAL SUPABASE CLIENT
# =============================================================================

@pytest_asyncio.fixture(loop_scope="function")
async def supabase():
    """Реальный Supabase клиент для интеграционных тестов."""
    from supabase._async.client import create_client as acreate_client
    settings = get_settings()
    # Создаём свежий клиент для каждого теста
    client = await acreate_client(
        settings.supabase_url,
        settings.supabase_key,
    )
    yield client
    # Закрываем HTTP клиент после теста
    await client.postgrest.aclose()


# =============================================================================
# MOCK SUPABASE (для unit-тестов)
# =============================================================================

@pytest.fixture
def mock_supabase():
    """Мок Supabase клиента."""
    return MagicMock()


def create_supabase_chain(data=None, single=False):
    """Создаёт цепочку моков для Supabase запросов.

    Args:
        data: Данные для возврата (список или словарь)
        single: Если True, data интерпретируется как одна запись
    """
    chain = MagicMock()
    chain.select = MagicMock(return_value=chain)
    chain.insert = MagicMock(return_value=chain)
    chain.update = MagicMock(return_value=chain)
    chain.upsert = MagicMock(return_value=chain)
    chain.delete = MagicMock(return_value=chain)
    chain.eq = MagicMock(return_value=chain)
    chain.neq = MagicMock(return_value=chain)
    chain.gte = MagicMock(return_value=chain)
    chain.lte = MagicMock(return_value=chain)
    chain.lt = MagicMock(return_value=chain)
    chain.in_ = MagicMock(return_value=chain)
    chain.ilike = MagicMock(return_value=chain)
    chain.order = MagicMock(return_value=chain)
    chain.limit = MagicMock(return_value=chain)
    chain.single = MagicMock(return_value=chain)
    chain.maybe_single = MagicMock(return_value=chain)

    result = MagicMock()
    if single and data is not None:
        result.data = [data]
    else:
        result.data = data if data is not None else []
    chain.execute = AsyncMock(return_value=result)

    return chain


# =============================================================================
# REAL SERVICES (для интеграционных тестов)
# =============================================================================

@pytest_asyncio.fixture
async def user_service(supabase):
    """Реальный UserService."""
    from app.services.users import UserService
    return UserService(supabase)


@pytest_asyncio.fixture
async def course_service(supabase):
    """Реальный CourseService."""
    from app.services.courses import CourseService
    return CourseService(supabase)


@pytest_asyncio.fixture
async def manager_service(supabase):
    """Реальный ManagerService."""
    from app.services.managers import ManagerService
    return ManagerService(supabase)


@pytest_asyncio.fixture
async def intake_logs_service(supabase):
    """Реальный IntakeLogsService."""
    from app.services.intake_logs import IntakeLogsService
    return IntakeLogsService(supabase)


@pytest_asyncio.fixture
async def topic_service(bot):
    """Реальный TopicService."""
    from app.services.topic import TopicService
    settings = get_settings()
    return TopicService(bot=bot, group_chat_id=settings.kok_group_id)


# =============================================================================
# TEST DATA FIXTURES (для интеграционных тестов)
# =============================================================================

@pytest_asyncio.fixture
async def test_manager(supabase):
    """Создаёт тестового менеджера и удаляет после теста."""
    telegram_id = random.randint(100000000, 999999999)

    result = await supabase.table("managers").insert({
        "telegram_id": telegram_id,
        "name": f"Test Manager {telegram_id}",
    }).execute()

    manager = result.data[0]
    yield manager

    # Cleanup
    await supabase.table("managers").delete().eq("id", manager["id"]).execute()


@pytest_asyncio.fixture
async def test_user(supabase, test_manager):
    """Создаёт тестового user без telegram_id."""
    result = await supabase.table("users").insert({
        "name": f"Тестова Девушка {random.randint(1000, 9999)}",
        "manager_id": test_manager["id"],
    }).execute()

    user = result.data[0]
    yield user

    # Cleanup
    await supabase.table("users").delete().eq("id", user["id"]).execute()


@pytest_asyncio.fixture
async def test_user_with_telegram(supabase, test_manager):
    """Создаёт тестового user с telegram_id."""
    telegram_id = random.randint(100000000, 999999999)

    result = await supabase.table("users").insert({
        "name": f"Тестова Девушка {random.randint(1000, 9999)}",
        "manager_id": test_manager["id"],
        "telegram_id": telegram_id,
    }).execute()

    user = result.data[0]
    yield user

    # Cleanup
    await supabase.table("users").delete().eq("id", user["id"]).execute()


@pytest_asyncio.fixture
async def test_active_course(supabase, test_user_with_telegram):
    """Создаёт активный курс."""
    today = get_tashkent_now().date().isoformat()
    intake_time = get_intake_time_in_window()

    result = await supabase.table("courses").insert({
        "user_id": test_user_with_telegram["id"],
        "invite_code": secrets.token_urlsafe(8),
        "invite_used": True,
        "status": "active",
        "start_date": today,
        "intake_time": intake_time,
        "current_day": 1,
        "total_days": 21,
    }).execute()

    course = result.data[0]
    yield course

    # Cleanup
    await supabase.table("intake_logs").delete().eq("course_id", course["id"]).execute()
    await supabase.table("courses").delete().eq("id", course["id"]).execute()


@pytest_asyncio.fixture
async def test_future_course(supabase, test_user_with_telegram):
    """Создаёт курс который ещё не начался."""
    tomorrow = (get_tashkent_now().date() + timedelta(days=1)).isoformat()

    result = await supabase.table("courses").insert({
        "user_id": test_user_with_telegram["id"],
        "invite_code": secrets.token_urlsafe(8),
        "invite_used": True,
        "status": "active",
        "start_date": tomorrow,
        "intake_time": "12:00",
        "current_day": 1,
        "total_days": 21,
    }).execute()

    course = result.data[0]
    yield course

    # Cleanup
    await supabase.table("courses").delete().eq("id", course["id"]).execute()


@pytest_asyncio.fixture
async def test_active_course_too_early(supabase, test_user_with_telegram):
    """Создаёт курс с intake_time в будущем (слишком рано для видео)."""
    today = get_tashkent_now().date().isoformat()
    intake_time = get_intake_time_too_early()

    result = await supabase.table("courses").insert({
        "user_id": test_user_with_telegram["id"],
        "invite_code": secrets.token_urlsafe(8),
        "invite_used": True,
        "status": "active",
        "start_date": today,
        "intake_time": intake_time,
        "current_day": 1,
        "total_days": 21,
    }).execute()

    course = result.data[0]
    yield course

    # Cleanup
    await supabase.table("courses").delete().eq("id", course["id"]).execute()


# =============================================================================
# GEMINI MOCKS (для тестов без реального API)
# =============================================================================

@pytest.fixture
def mock_gemini_confirmed():
    """Mock GeminiService который подтверждает видео."""
    service = MagicMock()
    service.verify_video = AsyncMock(return_value={
        "is_taking_pill": True,
        "confidence": 85,
        "reason": "Видно приём таблетки",
        "status": "confirmed",
    })
    return service


@pytest.fixture
def mock_gemini_pending():
    """Mock GeminiService который отправляет на проверку."""
    service = MagicMock()
    service.verify_video = AsyncMock(return_value={
        "is_taking_pill": False,
        "confidence": 50,
        "reason": "Не уверен",
        "status": "pending_review",
    })
    return service


# =============================================================================
# MOCK SERVICES
# =============================================================================

@pytest.fixture
def mock_course_service():
    """Мок CourseService."""
    service = MagicMock()
    service.create = AsyncMock(return_value={
        "id": 1,
        "user_id": 1,
        "invite_code": "test123",
        "status": "setup",
    })
    service.get_by_invite_code = AsyncMock(return_value=None)
    service.mark_invite_used = AsyncMock()
    service.get_active_by_user_id = AsyncMock(return_value=None)
    service.update = AsyncMock()
    service.get_by_id = AsyncMock(return_value=None)
    service.get_active_started = AsyncMock(return_value=[])
    service.set_refused = AsyncMock()
    return service


@pytest.fixture
def mock_user_service():
    """Мок UserService."""
    service = MagicMock()
    service.get_by_telegram_id = AsyncMock(return_value=None)
    service.set_telegram_id = AsyncMock()
    service.get_by_id = AsyncMock(return_value=None)
    service.set_topic_id = AsyncMock()
    service.get_by_name_and_manager = AsyncMock(return_value=None)
    service.get_active_by_manager = AsyncMock(return_value=[])
    service.get_telegram_id = AsyncMock(return_value=None)
    return service


@pytest.fixture
def mock_manager_service():
    """Мок ManagerService."""
    service = MagicMock()
    service.get_by_telegram_id = AsyncMock(return_value={
        "id": 1,
        "telegram_id": 123456789,
        "name": "Test Manager",
    })
    service.get_by_id = AsyncMock(return_value={
        "id": 1,
        "name": "Test Manager",
    })
    return service


@pytest.fixture
def mock_intake_logs_service():
    """Мок IntakeLogsService."""
    service = MagicMock()
    service.create = AsyncMock()
    service.get_by_course_and_day = AsyncMock(return_value=None)
    service.update_status = AsyncMock()
    return service


@pytest.fixture
def mock_topic_service():
    """Мок TopicService."""
    service = MagicMock()
    service.create_topic = AsyncMock(return_value=123)
    service.update_progress = AsyncMock()
    service.send_registration_info = AsyncMock(return_value=456)
    service.send_video = AsyncMock()
    service.send_review_buttons = AsyncMock()
    service.rename_topic_on_close = AsyncMock()
    service.send_closure_message = AsyncMock()
    service.close_topic = AsyncMock()
    service.remove_registration_buttons = AsyncMock()
    return service


@pytest.fixture
def mock_gemini_service():
    """Мок GeminiService."""
    service = MagicMock()
    service.verify_video = AsyncMock(return_value={
        "is_taking_pill": True,
        "confidence": 85,
        "reason": "Чётко видно приём таблетки",
        "status": "confirmed",
    })
    service.download_video = MagicMock()
    return service


@pytest.fixture
def mock_dashboard_service():
    """Мок DashboardService."""
    service = MagicMock()
    service.generate_full_dashboard = AsyncMock(return_value="📊 Test Dashboard")
    service.update_dashboard = AsyncMock()
    return service


@pytest.fixture
def mock_commands_messages_service():
    """Мок CommandsMessagesService."""
    service = MagicMock()
    service.add = AsyncMock()
    service.get_all = AsyncMock(return_value=[])
    service.delete_all = AsyncMock()
    return service


@pytest.fixture
def mock_stats_messages_service():
    """Мок StatsMessagesService."""
    service = MagicMock()
    service.get_by_type = AsyncMock(return_value=None)
    service.upsert = AsyncMock()
    service.update_timestamp = AsyncMock()
    return service


# =============================================================================
# MOCK BOT
# =============================================================================

@pytest.fixture
def mock_bot():
    """Mock бота."""
    mock = MagicMock()
    mock.send_message = AsyncMock(return_value=MagicMock(message_id=123))
    mock.edit_message_text = AsyncMock()
    mock.edit_message_reply_markup = AsyncMock()
    mock.edit_forum_topic = AsyncMock()
    mock.create_forum_topic = AsyncMock(return_value=MagicMock(message_thread_id=456))
    mock.close_forum_topic = AsyncMock()
    mock.delete_message = AsyncMock()
    mock.pin_chat_message = AsyncMock()
    mock.send_video_note = AsyncMock()
    mock.get_file = AsyncMock()
    mock.download_file = AsyncMock()
    mock.create_chat_invite_link = AsyncMock(return_value=MagicMock(invite_link="https://t.me/+test"))
    mock.session = MagicMock()
    mock.session.close = AsyncMock()
    return mock


@pytest.fixture
def bot(mock_bot):
    """Алиас для mock_bot."""
    return mock_bot


# =============================================================================
# MOCK REDIS
# =============================================================================

@pytest.fixture
def mock_redis():
    """Mock Redis."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.exists = AsyncMock(return_value=False)
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def redis(mock_redis):
    """Алиас для mock_redis."""
    return mock_redis


# =============================================================================
# FAKE AIOGRAM OBJECTS
# =============================================================================

@pytest.fixture
def fake_user():
    """Фабрика для создания fake User."""
    def _create(user_id: int = 123456789, first_name: str = "Test", username: str = "test_user"):
        return User(id=user_id, is_bot=False, first_name=first_name, username=username)
    return _create


@pytest.fixture
def fake_chat():
    """Фабрика для создания fake Chat."""
    def _create(chat_id: int = 123456789, chat_type: str = "private"):
        return Chat(id=chat_id, type=chat_type)
    return _create


@pytest.fixture
def mock_message(fake_user, fake_chat):
    """Фабрика для создания mock Message."""
    def _create(
        text: str = "test",
        user_id: int = 123456789,
        chat_id: int = None,
        message_id: int = 1,
        message_thread_id: int = None,
    ):
        chat_id = chat_id or user_id

        message = MagicMock(spec=Message)
        message.message_id = message_id
        message.message_thread_id = message_thread_id
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
    def _create(data: str = "test", user_id: int = 123456789, message_text: str = "test"):
        callback = MagicMock(spec=CallbackQuery)
        callback.id = "test_callback_id"
        callback.from_user = fake_user(user_id=user_id)
        callback.chat_instance = "test_instance"
        callback.data = data
        callback.message = mock_message(user_id=user_id, text=message_text)
        callback.answer = AsyncMock()
        return callback
    return _create


@pytest.fixture
def mock_video_message(fake_user, fake_chat):
    """Фабрика для создания mock Message с video_note."""
    def _create(user_id: int = 123456789, file_id: str = "test_video_file_id"):
        message = MagicMock(spec=Message)
        message.message_id = 1
        message.date = datetime.now()
        message.chat = fake_chat(chat_id=user_id, chat_type="private")
        message.from_user = fake_user(user_id=user_id)
        message.answer = AsyncMock()

        video_note = MagicMock()
        video_note.file_id = file_id
        message.video_note = video_note
        message.video = None

        return message
    return _create


@pytest.fixture
def mock_regular_video_message(fake_user, fake_chat):
    """Фабрика для создания mock Message с обычным video."""
    def _create(user_id: int = 123456789, file_id: str = "test_video_file_id"):
        message = MagicMock(spec=Message)
        message.message_id = 1
        message.date = datetime.now()
        message.chat = fake_chat(chat_id=user_id, chat_type="private")
        message.from_user = fake_user(user_id=user_id)
        message.answer = AsyncMock()

        video = MagicMock()
        video.file_id = file_id
        message.video = video
        message.video_note = None

        return message
    return _create


# =============================================================================
# FSM CONTEXT MOCK
# =============================================================================

@pytest.fixture
def mock_state():
    """Мок FSMContext."""
    state = MagicMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.set_data = AsyncMock()
    state.update_data = AsyncMock()
    return state


# =============================================================================
# TEST DATA FACTORIES
# =============================================================================

@pytest.fixture
def make_course():
    """Фабрика для создания тестовых курсов."""
    def _create(
        course_id: int = 1,
        user_id: int = 1,
        invite_code: str = None,
        invite_used: bool = False,
        status: str = "setup",
        cycle_day: int = 1,
        intake_time: str = "12:00",
        start_date: str = None,
        current_day: int = 1,
        total_days: int = 21,
        late_count: int = 0,
        allow_video: bool = False,
        registration_message_id: int = None,
    ):
        return {
            "id": course_id,
            "user_id": user_id,
            "invite_code": invite_code or secrets.token_urlsafe(8),
            "invite_used": invite_used,
            "status": status,
            "cycle_day": cycle_day,
            "intake_time": intake_time,
            "start_date": start_date or date.today().isoformat(),
            "current_day": current_day,
            "total_days": total_days,
            "late_count": late_count,
            "allow_video": allow_video,
            "registration_message_id": registration_message_id,
            "created_at": datetime.now().isoformat(),
        }
    return _create


@pytest.fixture
def make_user():
    """Фабрика для создания тестовых пользователей."""
    def _create(
        user_id: int = 1,
        telegram_id: int = None,
        name: str = "Тестова Мария Ивановна",
        manager_id: int = 1,
        topic_id: int = None,
    ):
        return {
            "id": user_id,
            "telegram_id": telegram_id,
            "name": name,
            "manager_id": manager_id,
            "topic_id": topic_id,
            "created_at": datetime.now().isoformat(),
        }
    return _create


@pytest.fixture
def make_manager():
    """Фабрика для создания тестовых менеджеров."""
    def _create(
        manager_id: int = 1,
        telegram_id: int = 123456789,
        name: str = "Test Manager",
    ):
        return {
            "id": manager_id,
            "telegram_id": telegram_id,
            "name": name,
            "created_at": datetime.now().isoformat(),
        }
    return _create


@pytest.fixture
def make_intake_log():
    """Фабрика для создания тестовых intake_logs."""
    def _create(
        log_id: int = 1,
        course_id: int = 1,
        day: int = 1,
        status: str = "taken",
        video_file_id: str = "test_file_id",
        verified_by: str = "ai",
        confidence: int = 85,
    ):
        return {
            "id": log_id,
            "course_id": course_id,
            "day": day,
            "status": status,
            "video_file_id": video_file_id,
            "verified_by": verified_by,
            "confidence": confidence,
            "created_at": datetime.now().isoformat(),
        }
    return _create