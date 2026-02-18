"""
Request tracking for mock Telegram server.

Stores all API calls made by the bot for inspection in tests.
Integrates with ChatState for stateful message tracking.
"""
import logging
from dataclasses import dataclass, field
from typing import Any

from tests.mock_server.chat_state import ChatState

logger = logging.getLogger("mock_server.tracker")


@dataclass
class TrackedRequest:
    """Single tracked API request."""

    method: str
    data: dict[str, Any]


@dataclass
class RequestTracker:
    """
    Tracks all requests made to the mock server.

    Integrates with ChatState for stateful message storage.
    """

    requests: list[TrackedRequest] = field(default_factory=list)
    chat_state: ChatState = field(default_factory=ChatState)

    def add_request(self, method: str, data: dict[str, Any]) -> None:
        """Add a request to the tracker."""
        self.requests.append(TrackedRequest(method=method, data=data))
        logger.debug("Tracked request: %s", method)

    def get_next_message_id(self) -> int:
        """Generate next message ID (delegated to ChatState)."""
        return self.chat_state._get_next_message_id()

    def get_requests_by_method(self, method: str) -> list[TrackedRequest]:
        """Get all requests for a specific method."""
        return [r for r in self.requests if r.method == method]

    def get_send_message_requests(self) -> list[TrackedRequest]:
        """Get all sendMessage requests."""
        return self.get_requests_by_method("sendMessage")

    def get_delete_message_requests(self) -> list[TrackedRequest]:
        """Get all deleteMessage requests."""
        return self.get_requests_by_method("deleteMessage")

    def get_edit_message_text_requests(self) -> list[TrackedRequest]:
        """Get all editMessageText requests."""
        return self.get_requests_by_method("editMessageText")

    def get_edit_message_reply_markup_requests(self) -> list[TrackedRequest]:
        """Get all editMessageReplyMarkup requests."""
        return self.get_requests_by_method("editMessageReplyMarkup")

    def get_answer_callback_query_requests(self) -> list[TrackedRequest]:
        """Get all answerCallbackQuery requests."""
        return self.get_requests_by_method("answerCallbackQuery")

    def get_send_photo_requests(self) -> list[TrackedRequest]:
        """Get all sendPhoto requests."""
        return self.get_requests_by_method("sendPhoto")

    def get_send_video_requests(self) -> list[TrackedRequest]:
        """Get all sendVideo requests."""
        return self.get_requests_by_method("sendVideo")

    def get_create_forum_topic_requests(self) -> list[TrackedRequest]:
        """Get all createForumTopic requests."""
        return self.get_requests_by_method("createForumTopic")

    def get_edit_forum_topic_requests(self) -> list[TrackedRequest]:
        """Get all editForumTopic requests."""
        return self.get_requests_by_method("editForumTopic")

    def get_close_forum_topic_requests(self) -> list[TrackedRequest]:
        """Get all closeForumTopic requests."""
        return self.get_requests_by_method("closeForumTopic")

    def get_pin_chat_message_requests(self) -> list[TrackedRequest]:
        """Get all pinChatMessage requests."""
        return self.get_requests_by_method("pinChatMessage")

    def clear(self) -> None:
        """Clear all tracked requests and chat state."""
        self.requests.clear()
        self.chat_state.clear()
        logger.debug("Cleared tracker and chat state")

    def clear_requests_only(self) -> None:
        """Clear only tracked requests, keep chat state."""
        self.requests.clear()
        logger.debug("Cleared requests only")
