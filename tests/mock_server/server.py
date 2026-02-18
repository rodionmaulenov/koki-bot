"""
Fake Telegram Bot API HTTP server.

Accepts requests in the same format as api.telegram.org and returns
realistic responses. Used for integration testing without real Telegram.

Includes forum topic support for koki-bot group topic testing.
"""
import json
import logging
from typing import Any

from aiohttp import web

from tests.mock_server.methods import (
    handle_answer_callback_query,
    handle_close_forum_topic,
    handle_create_forum_topic,
    handle_delete_message,
    handle_delete_messages,
    handle_edit_forum_topic,
    handle_edit_message_caption,
    handle_edit_message_media,
    handle_edit_message_reply_markup,
    handle_edit_message_text,
    handle_get_file,
    handle_pin_chat_message,
    handle_reopen_forum_topic,
    handle_send_document,
    handle_send_message,
    handle_send_photo,
    handle_send_video,
    handle_send_video_note,
)
from tests.mock_server.tracker import RequestTracker

logger = logging.getLogger("mock_server.server")


class FakeTelegramServer:
    """
    Fake Telegram Bot API server.

    Routes requests to appropriate handlers and tracks all API calls.
    Maintains stateful chat storage and forum topics via ChatState.
    """

    def __init__(self) -> None:
        self.tracker = RequestTracker()
        self.app = web.Application()
        self._setup_routes()

    def reset(self) -> None:
        """Reset server state for reuse between tests."""
        self.tracker.clear()

    def _setup_routes(self) -> None:
        """Setup URL routes for Telegram API methods."""
        self.app.router.add_post("/bot{token}/{method}", self._handle_request)
        self.app.router.add_get("/bot{token}/{method}", self._handle_request)
        # File download route (for bot.download)
        self.app.router.add_get("/file/bot{token}/{path:.*}", self._handle_file_download)

    async def _handle_request(self, request: web.Request) -> web.Response:
        """Handle incoming API request."""
        method = request.match_info["method"]

        data = await self._parse_request_data(request)

        self.tracker.add_request(method, data)

        response_data = self._route_method(method, data)

        logger.debug("API %s -> %s", method, "ok" if response_data.get("ok") else "error")

        status = 200
        if not response_data.get("ok") and "error_code" in response_data:
            status = response_data["error_code"]

        return web.json_response(response_data, status=status)

    @staticmethod
    async def _handle_file_download(request: web.Request) -> web.Response:
        """Handle file download requests (for bot.download)."""
        # Return fake video bytes
        return web.Response(
            body=b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100,
            content_type="video/mp4",
        )

    @staticmethod
    async def _parse_request_data(request: web.Request) -> dict[str, Any]:
        """Parse request body based on content type."""
        content_type = request.content_type

        if content_type == "application/json":
            try:
                return await request.json()
            except json.JSONDecodeError:
                return {}

        try:
            post_data = await request.post()
            result: dict[str, Any] = {}
            for key, value in post_data.items():
                if isinstance(value, str) and value and value[0] in "{[":
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = value
                else:
                    result[key] = value
            return result
        except ValueError:
            return {}

    def _route_method(self, method: str, data: dict[str, Any]) -> dict[str, Any]:
        """Route API method to appropriate handler."""
        chat_state = self.tracker.chat_state

        # Methods that use ChatState
        stateful_handlers: dict[str, Any] = {
            "sendMessage": lambda d: handle_send_message(d, chat_state),
            "deleteMessage": lambda d: handle_delete_message(d, chat_state),
            "deleteMessages": lambda d: handle_delete_messages(d, chat_state),
            "editMessageText": lambda d: handle_edit_message_text(d, chat_state),
            "editMessageReplyMarkup": lambda d: handle_edit_message_reply_markup(d, chat_state),
            "editMessageCaption": lambda d: handle_edit_message_caption(d, chat_state),
            "editMessageMedia": lambda d: handle_edit_message_media(d, chat_state),
            "sendPhoto": lambda d: handle_send_photo(d, chat_state),
            "sendVideo": lambda d: handle_send_video(d, chat_state),
            "sendVideoNote": lambda d: handle_send_video_note(d, chat_state),
            "sendDocument": lambda d: handle_send_document(d, chat_state),
            # Forum topics
            "createForumTopic": lambda d: handle_create_forum_topic(d, chat_state),
            "editForumTopic": lambda d: handle_edit_forum_topic(d, chat_state),
            "closeForumTopic": lambda d: handle_close_forum_topic(d, chat_state),
            "reopenForumTopic": lambda d: handle_reopen_forum_topic(d, chat_state),
            # Chat operations
            "pinChatMessage": lambda d: handle_pin_chat_message(d, chat_state),
        }

        # Methods without state
        stateless_handlers: dict[str, Any] = {
            "answerCallbackQuery": handle_answer_callback_query,
            "getFile": handle_get_file,
            "getMe": self._handle_get_me,
            "setMyCommands": self._handle_set_my_commands,
            "deleteMyCommands": self._handle_delete_my_commands,
            "deleteWebhook": self._handle_delete_webhook,
            "getUpdates": self._handle_get_updates,
        }

        handler = stateful_handlers.get(method)
        if handler is not None:
            return handler(data)

        handler = stateless_handlers.get(method)
        if handler is not None:
            if method in ("getMe", "setMyCommands", "deleteMyCommands", "deleteWebhook", "getUpdates"):
                return handler()
            return handler(data)

        return self._handle_unknown_method(method)

    @staticmethod
    def _handle_get_me() -> dict[str, Any]:
        """Handle getMe API call."""
        return {
            "ok": True,
            "result": {
                "id": 1234567890,
                "is_bot": True,
                "first_name": "TestBot",
                "username": "test_bot",
                "can_join_groups": True,
                "can_read_all_group_messages": False,
                "supports_inline_queries": False,
            },
        }

    @staticmethod
    def _handle_set_my_commands() -> dict[str, Any]:
        """Handle setMyCommands API call."""
        return {"ok": True, "result": True}

    @staticmethod
    def _handle_delete_my_commands() -> dict[str, Any]:
        """Handle deleteMyCommands API call."""
        return {"ok": True, "result": True}

    @staticmethod
    def _handle_delete_webhook() -> dict[str, Any]:
        """Handle deleteWebhook API call."""
        return {"ok": True, "result": True}

    @staticmethod
    def _handle_get_updates() -> dict[str, Any]:
        """Handle getUpdates API call (returns empty list)."""
        return {"ok": True, "result": []}

    @staticmethod
    def _handle_unknown_method(method: str) -> dict[str, Any]:
        """Handle unknown API method."""
        logger.warning("Unknown API method: %s", method)
        return {
            "ok": False,
            "error_code": 404,
            "description": f"Method '{method}' not implemented in mock server",
        }

    @property
    def chat_state(self):
        """Access chat state directly."""
        return self.tracker.chat_state

    def clear(self) -> None:
        """Clear all tracked requests and chat state."""
        self.tracker.clear()
