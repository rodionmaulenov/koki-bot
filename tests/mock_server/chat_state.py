"""
Stateful chat storage for mock Telegram server.

Maintains conversation history like real Telegram, enabling realistic testing
of message flows, edits, and deletions. Includes forum topic tracking.
"""
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("mock_server.chat_state")


@dataclass
class StoredMessage:
    """Message stored in chat state."""

    message_id: int
    chat_id: int
    from_user_id: int
    is_bot: bool
    text: str | None = None
    reply_markup: dict[str, Any] | None = None
    contact: dict[str, Any] | None = None
    photo: list[dict[str, Any]] | None = None
    video: dict[str, Any] | None = None
    video_note: dict[str, Any] | None = None
    animation: dict[str, Any] | None = None
    document: dict[str, Any] | None = None
    message_thread_id: int | None = None
    is_pinned: bool = False
    created_at: float = field(default_factory=time.time)
    edited_at: float | None = None
    is_deleted: bool = False

    def has_inline_keyboard(self) -> bool:
        """Check if message has inline keyboard."""
        if self.reply_markup is None:
            return False
        return "inline_keyboard" in self.reply_markup

    def get_button_callback_data(self, button_text: str) -> str | None:
        """Find callback_data for button with given text."""
        if not self.has_inline_keyboard():
            return None

        for row in self.reply_markup.get("inline_keyboard", []):
            for button in row:
                if button_text in button.get("text", ""):
                    return button.get("callback_data")
        return None

    def get_button_at(self, row: int, col: int) -> dict[str, Any] | None:
        """Get button at specific position."""
        if not self.has_inline_keyboard():
            return None

        keyboard = self.reply_markup.get("inline_keyboard", [])
        if row < 0 or row >= len(keyboard):
            return None

        row_buttons = keyboard[row]
        if col < 0 or col >= len(row_buttons):
            return None

        return row_buttons[col]


@dataclass
class ForumTopic:
    """Forum topic stored in chat state."""

    message_thread_id: int
    chat_id: int
    name: str
    icon_color: int = 7322096
    icon_custom_emoji_id: str | None = None
    is_closed: bool = False


class ChatState:
    """
    Maintains conversation state like real Telegram.

    Stores all messages sent in chats, tracks edits, deletions,
    and forum topics. Provides query methods for testing assertions.
    """

    def __init__(self) -> None:
        # chat_id -> message_id -> StoredMessage
        self._chats: dict[int, dict[int, StoredMessage]] = {}
        # chat_id -> message_thread_id -> ForumTopic
        self._forum_topics: dict[int, dict[int, ForumTopic]] = {}
        # Use random base to avoid collisions in parallel tests
        self._message_id_counter: int = random.randint(100000, 900000000)
        self._thread_id_counter: int = random.randint(1000, 9000)

    def _get_next_message_id(self) -> int:
        """Generate next unique message ID."""
        self._message_id_counter += 1
        return self._message_id_counter

    def _get_next_thread_id(self) -> int:
        """Generate next unique thread ID."""
        self._thread_id_counter += 1
        return self._thread_id_counter

    def _ensure_chat_exists(self, chat_id: int) -> None:
        """Create chat storage if it doesn't exist."""
        if chat_id not in self._chats:
            self._chats[chat_id] = {}

    def add_message(
        self,
        chat_id: int,
        from_user_id: int,
        is_bot: bool,
        text: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        contact: dict[str, Any] | None = None,
        photo: list[dict[str, Any]] | None = None,
        video: dict[str, Any] | None = None,
        video_note: dict[str, Any] | None = None,
        animation: dict[str, Any] | None = None,
        document: dict[str, Any] | None = None,
        message_id: int | None = None,
        message_thread_id: int | None = None,
    ) -> StoredMessage:
        """Add a new message to the chat."""
        self._ensure_chat_exists(chat_id)

        if message_id is None:
            message_id = self._get_next_message_id()
        elif message_id in self._chats[chat_id]:
            logger.error(
                "Duplicate message_id %d in chat %d - this should not happen",
                message_id,
                chat_id,
            )

        message = StoredMessage(
            message_id=message_id,
            chat_id=chat_id,
            from_user_id=from_user_id,
            is_bot=is_bot,
            text=text,
            reply_markup=reply_markup,
            contact=contact,
            photo=photo,
            video=video,
            video_note=video_note,
            animation=animation,
            document=document,
            message_thread_id=message_thread_id,
        )

        self._chats[chat_id][message_id] = message
        logger.debug(
            "Added message %d to chat %d: %s",
            message_id,
            chat_id,
            text[:50] if text else "(no text)",
        )

        return message

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> StoredMessage | None:
        """Edit message text."""
        message = self.get_message(chat_id, message_id)
        if message is None:
            logger.warning(
                "Cannot edit message %d in chat %d - not found",
                message_id,
                chat_id,
            )
            return None

        if message.is_deleted:
            logger.warning(
                "Cannot edit message %d in chat %d - already deleted",
                message_id,
                chat_id,
            )
            return None

        message.text = text
        message.edited_at = time.time()
        if reply_markup is not None:
            message.reply_markup = reply_markup

        logger.debug(
            "Edited message %d in chat %d: %s",
            message_id,
            chat_id,
            text[:50] if text else "(no text)",
        )

        return message

    def edit_message_reply_markup(
        self,
        chat_id: int,
        message_id: int,
        reply_markup: dict[str, Any] | None,
    ) -> StoredMessage | None:
        """Edit message reply markup (keyboard)."""
        message = self.get_message(chat_id, message_id)
        if message is None:
            logger.warning(
                "Cannot edit markup for message %d in chat %d - not found",
                message_id,
                chat_id,
            )
            return None

        if message.is_deleted:
            logger.warning(
                "Cannot edit markup for message %d in chat %d - already deleted",
                message_id,
                chat_id,
            )
            return None

        message.reply_markup = reply_markup
        message.edited_at = time.time()

        logger.debug(
            "Edited markup for message %d in chat %d",
            message_id,
            chat_id,
        )

        return message

    def delete_message(self, chat_id: int, message_id: int) -> bool:
        """Mark message as deleted."""
        message = self.get_message(chat_id, message_id)
        if message is None:
            logger.warning(
                "Cannot delete message %d in chat %d - not found",
                message_id,
                chat_id,
            )
            return False

        if message.is_deleted:
            logger.warning(
                "Message %d in chat %d already deleted",
                message_id,
                chat_id,
            )
            return False

        message.is_deleted = True
        logger.debug("Deleted message %d in chat %d", message_id, chat_id)

        return True

    def pin_message(self, chat_id: int, message_id: int) -> bool:
        """Pin a message in chat."""
        message = self.get_message(chat_id, message_id)
        if message is None:
            return False
        message.is_pinned = True
        logger.debug("Pinned message %d in chat %d", message_id, chat_id)
        return True

    # =========================================================================
    # Forum Topics
    # =========================================================================

    def create_forum_topic(
        self,
        chat_id: int,
        name: str,
        icon_color: int = 7322096,
        icon_custom_emoji_id: str | None = None,
    ) -> ForumTopic:
        """Create a forum topic in a chat."""
        if chat_id not in self._forum_topics:
            self._forum_topics[chat_id] = {}

        thread_id = self._get_next_thread_id()
        topic = ForumTopic(
            message_thread_id=thread_id,
            chat_id=chat_id,
            name=name,
            icon_color=icon_color,
            icon_custom_emoji_id=icon_custom_emoji_id,
        )
        self._forum_topics[chat_id][thread_id] = topic

        logger.debug(
            "Created forum topic %d in chat %d: %s",
            thread_id,
            chat_id,
            name,
        )
        return topic

    def edit_forum_topic(
        self,
        chat_id: int,
        message_thread_id: int,
        name: str | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> bool:
        """Edit a forum topic."""
        topic = self.get_forum_topic(chat_id, message_thread_id)
        if topic is None:
            # Telegram API returns True even for non-existent topics in some cases
            # But we'll track it if exists
            return True

        if name is not None:
            topic.name = name
        if icon_custom_emoji_id is not None:
            topic.icon_custom_emoji_id = icon_custom_emoji_id

        logger.debug(
            "Edited forum topic %d in chat %d: name=%s, icon=%s",
            message_thread_id,
            chat_id,
            name,
            icon_custom_emoji_id,
        )
        return True

    def close_forum_topic(self, chat_id: int, message_thread_id: int) -> bool:
        """Close a forum topic."""
        topic = self.get_forum_topic(chat_id, message_thread_id)
        if topic is not None:
            topic.is_closed = True
            logger.debug(
                "Closed forum topic %d in chat %d",
                message_thread_id,
                chat_id,
            )
        return True

    def reopen_forum_topic(self, chat_id: int, message_thread_id: int) -> bool:
        """Reopen a forum topic."""
        topic = self.get_forum_topic(chat_id, message_thread_id)
        if topic is not None:
            topic.is_closed = False
            logger.debug(
                "Reopened forum topic %d in chat %d",
                message_thread_id,
                chat_id,
            )
        return True

    def get_forum_topic(
        self, chat_id: int, message_thread_id: int
    ) -> ForumTopic | None:
        """Get forum topic by chat_id and thread_id."""
        if chat_id not in self._forum_topics:
            return None
        return self._forum_topics[chat_id].get(message_thread_id)

    def get_forum_topics(self, chat_id: int) -> list[ForumTopic]:
        """Get all forum topics for a chat."""
        if chat_id not in self._forum_topics:
            return []
        return list(self._forum_topics[chat_id].values())

    # =========================================================================
    # Query Methods
    # =========================================================================

    def get_message(self, chat_id: int, message_id: int) -> StoredMessage | None:
        """Get message by ID."""
        if chat_id not in self._chats:
            return None
        return self._chats[chat_id].get(message_id)

    def get_conversation(
        self,
        chat_id: int,
        include_deleted: bool = False,
    ) -> list[StoredMessage]:
        """Get all messages in chat ordered by creation time."""
        if chat_id not in self._chats:
            return []

        messages = list(self._chats[chat_id].values())

        if not include_deleted:
            messages = [m for m in messages if not m.is_deleted]

        return sorted(messages, key=lambda m: m.created_at)

    def get_thread_messages(
        self,
        chat_id: int,
        message_thread_id: int,
        include_deleted: bool = False,
    ) -> list[StoredMessage]:
        """Get all messages in a specific forum topic thread."""
        conversation = self.get_conversation(chat_id, include_deleted)
        return [m for m in conversation if m.message_thread_id == message_thread_id]

    def get_bot_messages(
        self,
        chat_id: int,
        include_deleted: bool = False,
    ) -> list[StoredMessage]:
        """Get all bot messages in chat."""
        conversation = self.get_conversation(chat_id, include_deleted)
        return [m for m in conversation if m.is_bot]

    def get_user_messages(
        self,
        chat_id: int,
        include_deleted: bool = False,
    ) -> list[StoredMessage]:
        """Get all user messages in chat."""
        conversation = self.get_conversation(chat_id, include_deleted)
        return [m for m in conversation if not m.is_bot]

    def find_message_with_button(
        self,
        chat_id: int,
        button_text: str,
    ) -> StoredMessage | None:
        """Find the most recent message containing a button with given text."""
        bot_messages = self.get_bot_messages(chat_id)

        # Search from newest to oldest
        for message in reversed(bot_messages):
            if message.get_button_callback_data(button_text) is not None:
                return message

        return None

    def get_last_bot_message(self, chat_id: int) -> StoredMessage | None:
        """Get the most recent bot message."""
        bot_messages = self.get_bot_messages(chat_id)
        return bot_messages[-1] if bot_messages else None

    def clear(self, chat_id: int | None = None) -> None:
        """Clear chat state."""
        if chat_id is not None:
            if chat_id in self._chats:
                self._chats[chat_id].clear()
            if chat_id in self._forum_topics:
                self._forum_topics[chat_id].clear()
            logger.debug("Cleared chat %d", chat_id)
        else:
            self._chats.clear()
            self._forum_topics.clear()
            self._message_id_counter = random.randint(100000, 900000000)
            self._thread_id_counter = random.randint(1000, 9000)
            logger.debug("Cleared all chats")

    def get_message_count(self, chat_id: int, include_deleted: bool = False) -> int:
        """Get number of messages in chat."""
        return len(self.get_conversation(chat_id, include_deleted))
