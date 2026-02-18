"""
Generate realistic Telegram API responses.

Creates proper JSON responses that aiogram can parse.
"""
import time
from typing import Any


def make_ok_response(result: Any) -> dict[str, Any]:
    """Create successful Telegram API response."""
    return {"ok": True, "result": result}


def make_error_response(description: str, error_code: int = 400) -> dict[str, Any]:
    """Create error Telegram API response."""
    return {
        "ok": False,
        "error_code": error_code,
        "description": description,
    }


def make_message_response(
    message_id: int,
    chat_id: int,
    text: str | None = None,
    reply_markup: dict[str, Any] | None = None,
    message_thread_id: int | None = None,
) -> dict[str, Any]:
    """Create Message object for sendMessage/editMessageText response."""
    message: dict[str, Any] = {
        "message_id": message_id,
        "date": int(time.time()),
        "chat": {
            "id": chat_id,
            "type": "private",
        },
        "from": {
            "id": 1234567890,
            "is_bot": True,
            "first_name": "TestBot",
            "username": "test_bot",
        },
    }

    if text is not None:
        message["text"] = text

    if message_thread_id is not None:
        message["message_thread_id"] = message_thread_id

    # Only include reply_markup if it's InlineKeyboardMarkup
    # ReplyKeyboardMarkup is not returned in Telegram API responses
    if reply_markup is not None and "inline_keyboard" in reply_markup:
        message["reply_markup"] = reply_markup

    return message


def make_true_response() -> dict[str, Any]:
    """Create response with result=True (for deleteMessage, answerCallbackQuery)."""
    return make_ok_response(True)
