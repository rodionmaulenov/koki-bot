"""
Forum topic and chat-related API method handlers.

Handles: createForumTopic, editForumTopic, closeForumTopic, reopenForumTopic,
         pinChatMessage, getFile

Telegram Bot API v9.4 (2026):
- createForumTopic returns ForumTopic object {message_thread_id, name, icon_color, icon_custom_emoji_id}
- editForumTopic, closeForumTopic, reopenForumTopic return True
- pinChatMessage returns True
- getFile returns File object {file_id, file_unique_id, file_size, file_path}
"""
import logging
from typing import Any

from tests.mock_server.chat_state import ChatState
from tests.mock_server.responses import make_error_response, make_ok_response, make_true_response

logger = logging.getLogger("mock_server.methods.forum")


def _safe_int(value: Any) -> int | None:
    """Safely convert value to int, return None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def handle_create_forum_topic(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle createForumTopic API call.

    Telegram API: https://core.telegram.org/bots/api#createforumtopic
    Returns ForumTopic object on success.
    """
    chat_id = _safe_int(data.get("chat_id"))
    name = data.get("name")
    icon_color = _safe_int(data.get("icon_color")) or 7322096
    icon_custom_emoji_id = data.get("icon_custom_emoji_id")

    if chat_id is None:
        return make_error_response("Bad Request: chat_id is required")

    if not name:
        return make_error_response("Bad Request: name is required")

    topic = chat_state.create_forum_topic(
        chat_id=chat_id,
        name=name,
        icon_color=icon_color,
        icon_custom_emoji_id=icon_custom_emoji_id,
    )

    logger.debug(
        "createForumTopic: chat=%d, name=%s, thread_id=%d",
        chat_id,
        name,
        topic.message_thread_id,
    )

    result: dict[str, Any] = {
        "message_thread_id": topic.message_thread_id,
        "name": topic.name,
        "icon_color": topic.icon_color,
    }
    if topic.icon_custom_emoji_id:
        result["icon_custom_emoji_id"] = topic.icon_custom_emoji_id

    return make_ok_response(result)


def handle_edit_forum_topic(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle editForumTopic API call.

    Telegram API: https://core.telegram.org/bots/api#editforumtopic
    Returns True on success.
    """
    chat_id = _safe_int(data.get("chat_id"))
    message_thread_id = _safe_int(data.get("message_thread_id"))

    if chat_id is None or message_thread_id is None:
        return make_error_response(
            "Bad Request: chat_id and message_thread_id are required"
        )

    name = data.get("name")
    icon_custom_emoji_id = data.get("icon_custom_emoji_id")

    chat_state.edit_forum_topic(
        chat_id=chat_id,
        message_thread_id=message_thread_id,
        name=name,
        icon_custom_emoji_id=icon_custom_emoji_id,
    )

    logger.debug(
        "editForumTopic: chat=%d, thread=%d, name=%s, icon=%s",
        chat_id,
        message_thread_id,
        name,
        icon_custom_emoji_id,
    )

    return make_true_response()


def handle_close_forum_topic(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle closeForumTopic API call.

    Telegram API: https://core.telegram.org/bots/api#closeforumtopic
    Returns True on success.
    """
    chat_id = _safe_int(data.get("chat_id"))
    message_thread_id = _safe_int(data.get("message_thread_id"))

    if chat_id is None or message_thread_id is None:
        return make_error_response(
            "Bad Request: chat_id and message_thread_id are required"
        )

    chat_state.close_forum_topic(chat_id, message_thread_id)

    logger.debug(
        "closeForumTopic: chat=%d, thread=%d",
        chat_id,
        message_thread_id,
    )

    return make_true_response()


def handle_reopen_forum_topic(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle reopenForumTopic API call.

    Telegram API: https://core.telegram.org/bots/api#reopenforumtopic
    Returns True on success.
    """
    chat_id = _safe_int(data.get("chat_id"))
    message_thread_id = _safe_int(data.get("message_thread_id"))

    if chat_id is None or message_thread_id is None:
        return make_error_response(
            "Bad Request: chat_id and message_thread_id are required"
        )

    chat_state.reopen_forum_topic(chat_id, message_thread_id)

    logger.debug(
        "reopenForumTopic: chat=%d, thread=%d",
        chat_id,
        message_thread_id,
    )

    return make_true_response()


def handle_pin_chat_message(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle pinChatMessage API call.

    Telegram API: https://core.telegram.org/bots/api#pinchatmessage
    Returns True on success.
    """
    chat_id = _safe_int(data.get("chat_id"))
    message_id = _safe_int(data.get("message_id"))

    if chat_id is None or message_id is None:
        return make_error_response(
            "Bad Request: chat_id and message_id are required"
        )

    chat_state.pin_message(chat_id, message_id)

    logger.debug(
        "pinChatMessage: chat=%d, message=%d",
        chat_id,
        message_id,
    )

    return make_true_response()


def handle_get_file(data: dict[str, Any]) -> dict[str, Any]:
    """Handle getFile API call.

    Telegram API: https://core.telegram.org/bots/api#getfile
    Returns File object on success.
    """
    file_id = data.get("file_id")

    if not file_id:
        return make_error_response("Bad Request: file_id is required")

    logger.debug("getFile: file_id=%s", file_id)

    return make_ok_response({
        "file_id": file_id,
        "file_unique_id": f"unique_{file_id}",
        "file_size": 102400,
        "file_path": f"videos/file_{file_id}.mp4",
    })
