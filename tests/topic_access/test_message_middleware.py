"""Tests for MessageMiddleware — 16 tests."""
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest

from topic_access.message_middleware import (
    ADD_ACTIVE_KEY_PREFIX,
    AUTO_DELETE_DELAY,
    MessageMiddleware,
)

from .conftest import THREAD_ID, USER_ID, make_message_event, make_telegram_bad_request

_PATCH = "topic_access.message_middleware.has_access"


def _mw(
    thread_id: int = THREAD_ID,
    repo: AsyncMock | None = None,
    redis: AsyncMock | None = None,
) -> MessageMiddleware:
    return MessageMiddleware(
        thread_id=thread_id,
        repository=repo or AsyncMock(),
        manager_repository=AsyncMock(),
        owner_repository=AsyncMock(),
        redis=redis or AsyncMock(),
    )


# ── __call__: pass-through and blocking ─────────────────────────────────────


async def test_wrong_thread_passes_through():
    """Different thread_id → handler called."""
    mw = _mw(thread_id=42)
    handler = AsyncMock(return_value="ok")
    event = make_message_event(thread_id=999)

    result = await mw(handler, event, {})

    handler.assert_called_once()
    assert result == "ok"


async def test_no_from_user_blocks_silently():
    """No from_user → returns None, no reply."""
    mw = _mw()
    handler = AsyncMock()
    event = make_message_event(user_id=None)

    result = await mw(handler, event, {})

    handler.assert_not_called()
    event.answer.assert_not_called()
    assert result is None


# ── __call__: access granted ────────────────────────────────────────────────


@patch(_PATCH, return_value=True)
async def test_access_granted_tracks_and_passes(_, mock_redis):
    """Access + no active flow → track message + handler."""
    repo = AsyncMock()
    redis = AsyncMock()
    redis.get.return_value = None  # no active flow
    mw = _mw(repo=repo, redis=redis)
    handler = AsyncMock(return_value="ok")
    event = make_message_event(message_id=555)

    result = await mw(handler, event, {})

    repo.add_message.assert_called_once_with(555)
    handler.assert_called_once()
    assert result == "ok"


@patch(_PATCH, return_value=True)
async def test_tracking_fails_still_passes(_):
    """repository.add_message throws → handler still called."""
    repo = AsyncMock()
    repo.add_message.side_effect = RuntimeError("DB error")
    redis = AsyncMock()
    redis.get.return_value = None
    mw = _mw(repo=repo, redis=redis)
    handler = AsyncMock(return_value="ok")
    event = make_message_event()

    result = await mw(handler, event, {})

    handler.assert_called_once()
    assert result == "ok"


@patch(_PATCH, return_value=True)
async def test_blocked_by_active_flow_deletes_message(_):
    """Access + another user's flow active → delete message."""
    redis = AsyncMock()
    redis.get.return_value = str(OTHER_USER := 999)
    mw = _mw(redis=redis)
    handler = AsyncMock()
    event = make_message_event(user_id=USER_ID)

    result = await mw(handler, event, {})

    event.delete.assert_called_once()
    handler.assert_not_called()
    assert result is None


@patch(_PATCH, return_value=True)
async def test_blocked_delete_fails_silently(_):
    """TelegramBadRequest on event.delete → no crash."""
    redis = AsyncMock()
    redis.get.return_value = "999"
    mw = _mw(redis=redis)
    handler = AsyncMock()
    event = make_message_event()
    event.delete.side_effect = TelegramBadRequest(
        method=AsyncMock(), message="already deleted",
    )

    result = await mw(handler, event, {})

    handler.assert_not_called()
    assert result is None


# ── __call__: access denied ─────────────────────────────────────────────────


@patch("topic_access.message_middleware.asyncio.create_task")
@patch(_PATCH, return_value=False)
async def test_no_access_replies_and_schedules_delete(_, mock_create_task):
    """No access → reply with text + schedule auto_delete."""
    mw = _mw()
    handler = AsyncMock()
    event = make_message_event(message_id=100)

    result = await mw(handler, event, {})

    handler.assert_not_called()
    event.answer.assert_called_once_with("🚫 У вас нет доступа")
    mock_create_task.assert_called_once()
    assert result is None


@patch("topic_access.message_middleware.asyncio.create_task")
@patch(_PATCH, return_value=False)
async def test_access_denied_correct_text(_, mock_create_task):
    """Custom access_denied_text is used in reply."""
    mw = MessageMiddleware(
        thread_id=THREAD_ID,
        repository=AsyncMock(),
        manager_repository=AsyncMock(),
        owner_repository=AsyncMock(),
        redis=AsyncMock(),
        access_denied_text="Custom denied!",
    )
    handler = AsyncMock()
    event = make_message_event()

    await mw(handler, event, {})

    event.answer.assert_called_once_with("Custom denied!")


# ── _is_blocked_by_active_flow ──────────────────────────────────────────────


async def test_is_blocked_no_active_key():
    """No Redis key → not blocked."""
    redis = AsyncMock()
    redis.get.return_value = None
    mw = _mw(redis=redis)

    assert await mw._is_blocked_by_active_flow(USER_ID) is False


async def test_is_blocked_same_user_not_blocked():
    """Active key = same user_id → not blocked."""
    redis = AsyncMock()
    redis.get.return_value = str(USER_ID)
    mw = _mw(redis=redis)

    assert await mw._is_blocked_by_active_flow(USER_ID) is False


async def test_is_blocked_different_user_blocked():
    """Active key = different user_id → blocked."""
    redis = AsyncMock()
    redis.get.return_value = "999"
    mw = _mw(redis=redis)

    assert await mw._is_blocked_by_active_flow(USER_ID) is True
    redis.get.assert_called_once_with(f"{ADD_ACTIVE_KEY_PREFIX}:{THREAD_ID}")


async def test_is_blocked_redis_error_not_blocked():
    """Redis throws → not blocked (graceful degradation)."""
    redis = AsyncMock()
    redis.get.side_effect = ConnectionError("Redis down")
    mw = _mw(redis=redis)

    assert await mw._is_blocked_by_active_flow(USER_ID) is False


async def test_is_blocked_corrupted_redis_value():
    """Non-numeric value in Redis → not blocked (ValueError caught)."""
    redis = AsyncMock()
    redis.get.return_value = "not_a_number"
    mw = _mw(redis=redis)

    assert await mw._is_blocked_by_active_flow(USER_ID) is False


# ── _auto_delete ────────────────────────────────────────────────────────────


@patch("topic_access.message_middleware.asyncio.sleep", new_callable=AsyncMock)
async def test_auto_delete_waits_then_deletes(mock_sleep):
    """Sleeps AUTO_DELETE_DELAY then deletes both messages."""
    bot = AsyncMock()
    chat_id = -100

    await MessageMiddleware._auto_delete(bot, chat_id, [10, 11])

    mock_sleep.assert_called_once_with(AUTO_DELETE_DELAY)
    assert bot.delete_message.call_count == 2
    bot.delete_message.assert_any_call(chat_id, 10)
    bot.delete_message.assert_any_call(chat_id, 11)


@patch("topic_access.message_middleware.asyncio.sleep", new_callable=AsyncMock)
async def test_auto_delete_handles_bad_request(mock_sleep):
    """TelegramBadRequest on one message → continues to next."""
    bot = AsyncMock()
    bot.delete_message.side_effect = [
        make_telegram_bad_request("not found"),
        True,
    ]

    await MessageMiddleware._auto_delete(bot, -100, [10, 11])

    assert bot.delete_message.call_count == 2