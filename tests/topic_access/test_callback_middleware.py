"""Tests for CallbackMiddleware — 9 tests."""
from unittest.mock import AsyncMock, patch

from topic_access.callback_middleware import CallbackMiddleware

from .conftest import THREAD_ID, make_callback_event

_PATCH = "topic_access.callback_middleware.has_access"


def _mw(thread_id: int = THREAD_ID) -> CallbackMiddleware:
    return CallbackMiddleware(
        thread_id=thread_id,
        manager_repository=AsyncMock(),
        owner_repository=AsyncMock(),
    )


# ── Pass-through branches ───────────────────────────────────────────────────


async def test_no_message_passes_through():
    """event.message=None → handler called (e.g. inline mode)."""
    mw = _mw()
    handler = AsyncMock(return_value="ok")
    event = make_callback_event(has_message=False)

    result = await mw(handler, event, {})

    handler.assert_called_once_with(event, {})
    assert result == "ok"


async def test_wrong_thread_passes_through():
    """Different thread_id → handler called."""
    mw = _mw(thread_id=42)
    handler = AsyncMock(return_value="ok")
    event = make_callback_event(thread_id=999)

    result = await mw(handler, event, {})

    handler.assert_called_once()
    assert result == "ok"


async def test_message_without_thread_passes_through():
    """message_thread_id=None (not in any topic) → passes through."""
    mw = _mw(thread_id=42)
    handler = AsyncMock(return_value="ok")
    event = make_callback_event(thread_id=None)

    result = await mw(handler, event, {})

    handler.assert_called_once()
    assert result == "ok"


# ── Blocking branches ───────────────────────────────────────────────────────


async def test_no_from_user_blocks_with_popup():
    """No from_user → popup + handler NOT called."""
    mw = _mw()
    handler = AsyncMock()
    event = make_callback_event(user_id=None)

    result = await mw(handler, event, {})

    handler.assert_not_called()
    event.answer.assert_called_once_with("🚫 У вас нет доступа", show_alert=True)
    assert result is None


@patch(_PATCH, return_value=False)
async def test_stranger_blocked_with_popup(_):
    """No access → popup + handler NOT called."""
    mw = _mw()
    handler = AsyncMock()
    event = make_callback_event()

    result = await mw(handler, event, {})

    handler.assert_not_called()
    event.answer.assert_called_once_with("🚫 У вас нет доступа", show_alert=True)
    assert result is None


# ── Access granted ──────────────────────────────────────────────────────────


@patch(_PATCH, return_value=True)
async def test_access_granted_passes_through(_):
    """has_access=True → handler called, return value preserved."""
    mw = _mw()
    handler = AsyncMock(return_value={"key": "value"})
    event = make_callback_event()

    result = await mw(handler, event, {})

    handler.assert_called_once_with(event, {})
    assert result == {"key": "value"}


@patch(_PATCH, return_value=True)
async def test_has_access_called_with_correct_args(mock_has_access):
    """has_access receives from_user.id and both repos."""
    mw = _mw()
    handler = AsyncMock()
    event = make_callback_event(user_id=777)

    await mw(handler, event, {})

    mock_has_access.assert_called_once_with(
        777, mw._manager_repository, mw._owner_repository,
    )


# ── show_alert verification ────────────────────────────────────────────────


@patch(_PATCH, return_value=False)
async def test_show_alert_is_true_not_false(_):
    """Popup (show_alert=True), NOT toast (show_alert=False)."""
    mw = _mw()
    handler = AsyncMock()
    event = make_callback_event()

    await mw(handler, event, {})

    _, kwargs = event.answer.call_args
    assert kwargs["show_alert"] is True


async def test_custom_access_denied_text():
    """Custom toast text is used."""
    mw = CallbackMiddleware(
        thread_id=THREAD_ID,
        manager_repository=AsyncMock(),
        owner_repository=AsyncMock(),
        access_denied_toast="Custom denied!",
    )
    handler = AsyncMock()
    event = make_callback_event(user_id=None)

    await mw(handler, event, {})

    event.answer.assert_called_once_with("Custom denied!", show_alert=True)