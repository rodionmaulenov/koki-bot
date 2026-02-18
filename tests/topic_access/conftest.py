"""Shared fixtures and helpers for topic_access tests."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from models.commands_message import CommandsMessage

# ── Constants ───────────────────────────────────────────────────────────────

THREAD_ID = 42
CHAT_ID = -1001234567890
USER_ID = 123456789


# ── Factory functions ───────────────────────────────────────────────────────


def make_user(user_id: int = USER_ID) -> MagicMock:
    """Create a mock Telegram User."""
    user = MagicMock(spec=User)
    user.id = user_id
    return user


def make_callback_event(
    thread_id: int | None = THREAD_ID,
    user_id: int | None = USER_ID,
    has_message: bool = True,
) -> AsyncMock:
    """Create a mock CallbackQuery event."""
    event = AsyncMock(spec=CallbackQuery)

    if has_message:
        event.message = MagicMock()
        event.message.message_thread_id = thread_id
    else:
        event.message = None

    if user_id is not None:
        event.from_user = make_user(user_id)
    else:
        event.from_user = None

    # Explicitly set answer as AsyncMock (spec doesn't auto-detect coroutines)
    event.answer = AsyncMock()

    return event


def make_message_event(
    thread_id: int | None = THREAD_ID,
    user_id: int | None = USER_ID,
    message_id: int = 1000,
    chat_id: int = CHAT_ID,
) -> AsyncMock:
    """Create a mock Message event for middleware."""
    event = AsyncMock(spec=Message)
    event.message_thread_id = thread_id
    event.message_id = message_id

    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    event.chat = chat

    event.bot = AsyncMock()

    if user_id is not None:
        event.from_user = make_user(user_id)
    else:
        event.from_user = None

    # Explicitly set async methods (spec doesn't auto-detect coroutines)
    reply = MagicMock(spec=Message)
    reply.message_id = message_id + 1
    event.answer = AsyncMock(return_value=reply)
    event.delete = AsyncMock()

    return event


def make_bot_message(
    chat_id: int = CHAT_ID,
    thread_id: int | None = THREAD_ID,
    message_id: int = 500,
) -> MagicMock:
    """Create a mock Message result from bot API call."""
    msg = MagicMock(spec=Message)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = chat_id
    msg.message_thread_id = thread_id
    msg.message_id = message_id
    return msg


def make_cmd_msg(db_id: int, message_id: int) -> CommandsMessage:
    """Create a CommandsMessage model for service tests."""
    return CommandsMessage(
        id=db_id,
        message_id=message_id,
        bot_type="test",
        is_menu=False,
        created_at=datetime(2025, 1, 1),
    )


def make_telegram_bad_request(text: str = "Bad Request") -> Exception:
    """Create TelegramBadRequest with mock method."""
    from aiogram.exceptions import TelegramBadRequest

    mock_method = MagicMock()
    mock_method.__class__.__name__ = "TestMethod"
    return TelegramBadRequest(method=mock_method, message=text)


def make_telegram_forbidden(text: str = "Forbidden") -> Exception:
    """Create TelegramForbiddenError with mock method."""
    from aiogram.exceptions import TelegramForbiddenError

    mock_method = MagicMock()
    mock_method.__class__.__name__ = "TestMethod"
    return TelegramForbiddenError(method=mock_method, message=text)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_manager_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_owner_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_commands_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_redis() -> AsyncMock:
    return AsyncMock()