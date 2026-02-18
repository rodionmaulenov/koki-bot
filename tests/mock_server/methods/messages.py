"""
Message-related API method handlers.

Handles: sendMessage, deleteMessage, deleteMessages, editMessageText, editMessageReplyMarkup
"""
import logging
from typing import Any

from tests.mock_server.chat_state import ChatState
from tests.mock_server.responses import (
    make_error_response,
    make_message_response,
    make_ok_response,
    make_true_response,
)

logger = logging.getLogger("mock_server.methods.messages")


def _safe_int(value: Any) -> int | None:
    """Safely convert value to int, return None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def handle_send_message(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle sendMessage API call."""
    chat_id = _safe_int(data.get("chat_id"))
    text = data.get("text")
    reply_markup = data.get("reply_markup")
    message_thread_id = _safe_int(data.get("message_thread_id"))

    if chat_id is None:
        return make_error_response("Bad Request: chat_id is required")

    stored = chat_state.add_message(
        chat_id=chat_id,
        from_user_id=1234567890,
        is_bot=True,
        text=text,
        reply_markup=reply_markup,
        message_thread_id=message_thread_id,
    )

    logger.debug(
        "sendMessage to chat %d: message_id=%d, text=%s",
        chat_id,
        stored.message_id,
        text[:50] if text else "(no text)",
    )

    message = make_message_response(
        message_id=stored.message_id,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        message_thread_id=message_thread_id,
    )

    return make_ok_response(message)


def handle_delete_message(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle deleteMessage API call."""
    chat_id = _safe_int(data.get("chat_id"))
    message_id = _safe_int(data.get("message_id"))

    if chat_id is None or message_id is None:
        return make_error_response(
            "Bad Request: chat_id and message_id are required"
        )

    chat_state.delete_message(chat_id, message_id)

    logger.debug("deleteMessage: chat=%d, message=%d", chat_id, message_id)

    return make_true_response()


def handle_delete_messages(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle deleteMessages API call (batch delete)."""
    chat_id = _safe_int(data.get("chat_id"))
    message_ids = data.get("message_ids", [])

    if chat_id is None:
        return make_error_response("Bad Request: chat_id is required")

    if not message_ids:
        return make_error_response("Bad Request: message_ids is required")

    for message_id in message_ids:
        msg_id = _safe_int(message_id)
        if msg_id is not None:
            chat_state.delete_message(chat_id, msg_id)

    logger.debug("deleteMessages: chat=%d, messages=%s", chat_id, message_ids)

    return make_true_response()


def handle_edit_message_text(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle editMessageText API call."""
    chat_id = _safe_int(data.get("chat_id"))
    message_id = _safe_int(data.get("message_id"))
    text = data.get("text")
    reply_markup = data.get("reply_markup")

    if chat_id is None or message_id is None:
        return make_error_response(
            "Bad Request: chat_id and message_id are required"
        )

    if text is None:
        return make_error_response("Bad Request: text is required")

    stored = chat_state.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=reply_markup,
    )

    if stored is None:
        return make_error_response(
            "message not found or already deleted",
            error_code=400,
        )

    logger.debug(
        "editMessageText: chat=%d, message=%d, text=%s",
        chat_id,
        message_id,
        text[:50] if text else "(no text)",
    )

    message_thread_id = stored.message_thread_id

    message = make_message_response(
        message_id=message_id,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        message_thread_id=message_thread_id,
    )

    return make_ok_response(message)


def handle_edit_message_reply_markup(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle editMessageReplyMarkup API call."""
    chat_id = _safe_int(data.get("chat_id"))
    message_id = _safe_int(data.get("message_id"))
    reply_markup = data.get("reply_markup")

    if chat_id is None or message_id is None:
        return make_error_response(
            "Bad Request: chat_id and message_id are required"
        )

    stored = chat_state.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=reply_markup,
    )

    if stored is None:
        return make_error_response(
            "message not found or already deleted",
            error_code=400,
        )

    logger.debug(
        "editMessageReplyMarkup: chat=%d, message=%d",
        chat_id,
        message_id,
    )

    message = make_message_response(
        message_id=message_id,
        chat_id=chat_id,
        text=stored.text,
        reply_markup=reply_markup,
        message_thread_id=stored.message_thread_id,
    )

    return make_ok_response(message)
