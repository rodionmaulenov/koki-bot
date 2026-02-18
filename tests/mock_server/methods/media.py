"""
Media-related API method handlers.

Handles: sendPhoto, sendVideo, sendVideoNote, sendDocument,
         editMessageCaption, editMessageMedia
"""
import logging
import time
from typing import Any

from tests.mock_server.chat_state import ChatState
from tests.mock_server.responses import make_error_response, make_ok_response

logger = logging.getLogger("mock_server.methods.media")


def _safe_int(value: Any) -> int | None:
    """Safely convert value to int, return None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _make_photo_sizes(file_id: str) -> list[dict[str, Any]]:
    """Create fake photo sizes array."""
    return [
        {
            "file_id": f"{file_id}_small",
            "file_unique_id": f"unique_{file_id}_small",
            "width": 90,
            "height": 90,
            "file_size": 1024,
        },
        {
            "file_id": file_id,
            "file_unique_id": f"unique_{file_id}",
            "width": 800,
            "height": 600,
            "file_size": 102400,
        },
    ]


def _make_video_data(file_id: str) -> dict[str, Any]:
    """Create fake video data."""
    return {
        "file_id": file_id,
        "file_unique_id": f"unique_{file_id}",
        "width": 1920,
        "height": 1080,
        "duration": 30,
        "file_size": 1024000,
        "mime_type": "video/mp4",
    }


def _make_video_note_data(file_id: str) -> dict[str, Any]:
    """Create fake video note data."""
    return {
        "file_id": file_id,
        "file_unique_id": f"unique_{file_id}",
        "length": 240,
        "duration": 15,
        "file_size": 512000,
    }


def _make_document_data(file_id: str) -> dict[str, Any]:
    """Create fake document data."""
    return {
        "file_id": file_id,
        "file_unique_id": f"unique_{file_id}",
        "file_name": "document.pdf",
        "mime_type": "application/pdf",
        "file_size": 204800,
    }


def _build_media_message(
    stored_message_id: int,
    created_at: float,
    chat_id: int,
    message_thread_id: int | None = None,
    caption: str | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build base message dict for media responses."""
    message: dict[str, Any] = {
        "message_id": stored_message_id,
        "date": int(created_at),
        "chat": {"id": chat_id, "type": "private"},
        "from": {
            "id": 1234567890,
            "is_bot": True,
            "first_name": "TestBot",
            "username": "test_bot",
        },
    }

    if caption:
        message["caption"] = caption
    if message_thread_id:
        message["message_thread_id"] = message_thread_id
    if reply_markup and "inline_keyboard" in reply_markup:
        message["reply_markup"] = reply_markup

    return message


def handle_send_photo(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle sendPhoto API call."""
    chat_id = _safe_int(data.get("chat_id"))
    caption = data.get("caption")
    reply_markup = data.get("reply_markup")
    message_thread_id = _safe_int(data.get("message_thread_id"))

    if chat_id is None:
        return make_error_response("Bad Request: chat_id is required")

    file_id = f"photo_{int(time.time())}"
    photo_sizes = _make_photo_sizes(file_id)

    stored = chat_state.add_message(
        chat_id=chat_id,
        from_user_id=1234567890,
        is_bot=True,
        text=caption,
        reply_markup=reply_markup,
        photo=photo_sizes,
        message_thread_id=message_thread_id,
    )

    message = _build_media_message(
        stored.message_id, stored.created_at, chat_id,
        message_thread_id, caption, reply_markup,
    )
    message["photo"] = photo_sizes

    return make_ok_response(message)


def handle_send_video(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle sendVideo API call."""
    chat_id = _safe_int(data.get("chat_id"))
    caption = data.get("caption")
    reply_markup = data.get("reply_markup")
    message_thread_id = _safe_int(data.get("message_thread_id"))

    if chat_id is None:
        return make_error_response("Bad Request: chat_id is required")

    file_id = f"video_{int(time.time())}"
    video_data = _make_video_data(file_id)

    stored = chat_state.add_message(
        chat_id=chat_id,
        from_user_id=1234567890,
        is_bot=True,
        text=caption,
        reply_markup=reply_markup,
        video=video_data,
        message_thread_id=message_thread_id,
    )

    message = _build_media_message(
        stored.message_id, stored.created_at, chat_id,
        message_thread_id, caption, reply_markup,
    )
    message["video"] = video_data

    return make_ok_response(message)


def handle_send_video_note(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle sendVideoNote API call."""
    chat_id = _safe_int(data.get("chat_id"))
    message_thread_id = _safe_int(data.get("message_thread_id"))

    if chat_id is None:
        return make_error_response("Bad Request: chat_id is required")

    file_id = f"video_note_{int(time.time())}"
    video_note_data = _make_video_note_data(file_id)

    stored = chat_state.add_message(
        chat_id=chat_id,
        from_user_id=1234567890,
        is_bot=True,
        video_note=video_note_data,
        message_thread_id=message_thread_id,
    )

    message = _build_media_message(
        stored.message_id, stored.created_at, chat_id,
        message_thread_id,
    )
    message["video_note"] = video_note_data

    return make_ok_response(message)


def handle_send_document(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle sendDocument API call."""
    chat_id = _safe_int(data.get("chat_id"))
    caption = data.get("caption")
    reply_markup = data.get("reply_markup")
    message_thread_id = _safe_int(data.get("message_thread_id"))

    if chat_id is None:
        return make_error_response("Bad Request: chat_id is required")

    file_id = f"document_{int(time.time())}"
    document_data = _make_document_data(file_id)

    stored = chat_state.add_message(
        chat_id=chat_id,
        from_user_id=1234567890,
        is_bot=True,
        text=caption,
        reply_markup=reply_markup,
        document=document_data,
        message_thread_id=message_thread_id,
    )

    message = _build_media_message(
        stored.message_id, stored.created_at, chat_id,
        message_thread_id, caption, reply_markup,
    )
    message["document"] = document_data

    return make_ok_response(message)


def handle_edit_message_caption(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle editMessageCaption API call."""
    chat_id = _safe_int(data.get("chat_id"))
    message_id = _safe_int(data.get("message_id"))
    caption = data.get("caption")
    reply_markup = data.get("reply_markup")

    if chat_id is None or message_id is None:
        return make_error_response(
            "Bad Request: chat_id and message_id are required"
        )

    stored = chat_state.get_message(chat_id, message_id)
    if stored is None:
        return make_error_response(
            "message not found or already deleted",
            error_code=400,
        )

    message = _build_media_message(
        message_id, stored.created_at, chat_id,
        stored.message_thread_id, caption, reply_markup,
    )
    message["photo"] = _make_photo_sizes("edited_photo")

    return make_ok_response(message)


def handle_edit_message_media(
    data: dict[str, Any],
    chat_state: ChatState,
) -> dict[str, Any]:
    """Handle editMessageMedia API call."""
    chat_id = _safe_int(data.get("chat_id"))
    message_id = _safe_int(data.get("message_id"))
    reply_markup = data.get("reply_markup")

    if chat_id is None or message_id is None:
        return make_error_response(
            "Bad Request: chat_id and message_id are required"
        )

    stored = chat_state.get_message(chat_id, message_id)
    if stored is None:
        return make_error_response(
            "message not found or already deleted",
            error_code=400,
        )

    message = _build_media_message(
        message_id, stored.created_at, chat_id,
        stored.message_thread_id, reply_markup=reply_markup,
    )
    message["photo"] = _make_photo_sizes("new_media")

    return make_ok_response(message)
