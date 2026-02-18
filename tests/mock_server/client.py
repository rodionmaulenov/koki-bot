"""
High-level test client for integration tests.

Provides simple API for simulating user actions and inspecting bot responses.
Includes forum topic support for koki-bot group topic testing.
"""
import logging
from typing import Any

from aiohttp.test_utils import TestServer
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from tests.mock_server.chat_state import ChatState, ForumTopic, StoredMessage
from tests.mock_server.server import FakeTelegramServer
from tests.mock_server.tracker import TrackedRequest
from tests.mock_server.updates import UpdateBuilder

logger = logging.getLogger("mock_server.client")


class ButtonNotFoundError(Exception):
    """Raised when a button cannot be found in the chat."""


class NoMessagesError(Exception):
    """Raised when trying to access messages in an empty chat."""


class MockBot:
    """
    Lightweight mock Bot for service/worker tests.

    Provides a real Bot instance pointing to the mock server.
    """

    def __init__(self) -> None:
        self._server = FakeTelegramServer()
        self._test_server: TestServer | None = None
        self._bot: Bot | None = None

    async def __aenter__(self) -> "MockBot":
        """Start the mock server and create bot."""
        self._test_server = TestServer(self._server.app)
        await self._test_server.start_server()

        server_url = f"http://{self._test_server.host}:{self._test_server.port}"

        local_api = TelegramAPIServer.from_base(server_url)
        session = AiohttpSession(api=local_api)
        self._bot = Bot(token="1234567890:TEST_TOKEN_FOR_MOCK_SERVER", session=session)

        logger.debug("MockBot started at %s", server_url)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Stop the mock server and close bot session."""
        if self._bot is not None:
            await self._bot.session.close()
        if self._test_server is not None:
            await self._test_server.close()
        logger.debug("MockBot stopped")

    @property
    def bot(self) -> Bot:
        """Get the bot instance."""
        if self._bot is None:
            raise RuntimeError("MockBot not started. Use 'async with' context.")
        return self._bot

    @property
    def tracker(self):
        """Access the request tracker."""
        return self._server.tracker

    @property
    def chat_state(self) -> ChatState:
        """Access the chat state."""
        return self._server.chat_state

    def get_sent_messages(self) -> list[TrackedRequest]:
        """Get all sendMessage requests."""
        return self._server.tracker.get_send_message_requests()

    def get_deleted_messages(self) -> list[TrackedRequest]:
        """Get all deleteMessage requests."""
        return self._server.tracker.get_delete_message_requests()

    def get_edit_message_text_requests(self) -> list[TrackedRequest]:
        """Get all editMessageText requests."""
        return self._server.tracker.get_edit_message_text_requests()

    def get_callback_answers(self) -> list[TrackedRequest]:
        """Get all answerCallbackQuery requests."""
        return self._server.tracker.get_answer_callback_query_requests()

    def clear(self) -> None:
        """Clear all tracked requests and chat state."""
        self._server.clear()


class MockTelegramBot:
    """
    Test client for integration tests.

    Simulates user interactions and captures bot responses.
    Supports both private chat and group topic testing.
    """

    def __init__(
        self,
        dispatcher: Dispatcher,
        user_id: int = 123456789,
        chat_id: int | None = None,
        chat_type: str = "private",
        message_thread_id: int | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.user_id = user_id
        self.chat_id = chat_id if chat_id is not None else user_id
        self.chat_type = chat_type
        self.message_thread_id = message_thread_id

        self._server = FakeTelegramServer()
        self._test_server: TestServer | None = None
        self._bot: Bot | None = None
        self._update_builder = UpdateBuilder(
            user_id=user_id,
            chat_id=self.chat_id,
            chat_type=chat_type,
            message_thread_id=message_thread_id,
        )

    async def __aenter__(self) -> "MockTelegramBot":
        """Start the mock server and create bot."""
        self._test_server = TestServer(self._server.app)
        await self._test_server.start_server()

        server_url = f"http://{self._test_server.host}:{self._test_server.port}"

        local_api = TelegramAPIServer.from_base(server_url)
        session = AiohttpSession(api=local_api)
        self._bot = Bot(token="1234567890:TEST_TOKEN_FOR_MOCK_SERVER", session=session)

        logger.debug("MockTelegramBot started at %s", server_url)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Stop the mock server and close bot session."""
        if self._bot is not None:
            await self._bot.session.close()
        if self._test_server is not None:
            await self._test_server.close()
        logger.debug("MockTelegramBot stopped")

    @property
    def bot(self) -> Bot:
        """Get the bot instance."""
        if self._bot is None:
            raise RuntimeError("MockTelegramBot not started. Use 'async with' context.")
        return self._bot

    @property
    def chat_state(self) -> ChatState:
        """Access the chat state directly."""
        return self._server.chat_state

    # =========================================================================
    # User Actions
    # =========================================================================

    async def send_message(self, text: str) -> None:
        """Simulate user sending a text message."""
        update = self._update_builder.make_message_update(text)

        self.chat_state.add_message(
            chat_id=self.chat_id,
            from_user_id=self.user_id,
            is_bot=False,
            text=text,
            message_id=update.message.message_id,
            message_thread_id=self.message_thread_id,
        )

        await self.dispatcher.feed_update(self.bot, update)
        logger.debug("User sent message: %s", text[:50] if text else "(empty)")

    async def send_video(
        self,
        file_id: str = "test_video_id",
        caption: str | None = None,
        duration: int = 30,
    ) -> None:
        """Simulate user sending a video."""
        update = self._update_builder.make_video_update(
            file_id=file_id, caption=caption, duration=duration,
        )

        self.chat_state.add_message(
            chat_id=self.chat_id,
            from_user_id=self.user_id,
            is_bot=False,
            text=caption,
            video={"file_id": file_id},
            message_id=update.message.message_id,
            message_thread_id=self.message_thread_id,
        )

        await self.dispatcher.feed_update(self.bot, update)
        logger.debug("User sent video: %s", file_id)

    async def send_video_note(
        self,
        file_id: str = "test_video_note_id",
        duration: int = 15,
    ) -> None:
        """Simulate user sending a video note (round video)."""
        update = self._update_builder.make_video_note_update(
            file_id=file_id, duration=duration,
        )

        self.chat_state.add_message(
            chat_id=self.chat_id,
            from_user_id=self.user_id,
            is_bot=False,
            video_note={"file_id": file_id},
            message_id=update.message.message_id,
            message_thread_id=self.message_thread_id,
        )

        await self.dispatcher.feed_update(self.bot, update)
        logger.debug("User sent video note: %s", file_id)

    async def send_photo(
        self,
        file_id: str = "test_photo_id",
        caption: str | None = None,
    ) -> None:
        """Simulate user sending a photo."""
        update = self._update_builder.make_photo_update(file_id=file_id, caption=caption)

        self.chat_state.add_message(
            chat_id=self.chat_id,
            from_user_id=self.user_id,
            is_bot=False,
            text=caption,
            photo=[{"file_id": file_id}],
            message_id=update.message.message_id,
            message_thread_id=self.message_thread_id,
        )

        await self.dispatcher.feed_update(self.bot, update)
        logger.debug("User sent photo: %s", file_id)

    async def send_document(
        self,
        file_id: str = "test_document_id",
        file_name: str | None = "document.pdf",
        mime_type: str = "application/pdf",
        caption: str | None = None,
    ) -> None:
        """Simulate user sending a document."""
        update = self._update_builder.make_document_update(
            file_id=file_id, file_name=file_name,
            mime_type=mime_type, caption=caption,
        )

        self.chat_state.add_message(
            chat_id=self.chat_id,
            from_user_id=self.user_id,
            is_bot=False,
            text=caption,
            document={"file_id": file_id, "file_name": file_name, "mime_type": mime_type},
            message_id=update.message.message_id,
            message_thread_id=self.message_thread_id,
        )

        await self.dispatcher.feed_update(self.bot, update)
        logger.debug("User sent document: %s", file_name)

    async def click_button(self, callback_data: str, message_id: int | None = None) -> None:
        """Simulate user clicking inline button by callback_data."""
        if message_id is None:
            last_bot_msg = self.chat_state.get_last_bot_message(self.chat_id)
            if last_bot_msg is None:
                raise NoMessagesError("No bot messages in chat to click button on")
            message_id = last_bot_msg.message_id

        update = self._update_builder.make_callback_update(
            callback_data=callback_data,
            message_id=message_id,
        )

        await self.dispatcher.feed_update(self.bot, update)
        logger.debug("User clicked button: %s on message %d", callback_data, message_id)

    async def click_button_by_text(self, button_text: str) -> None:
        """Simulate user clicking inline button by visible text."""
        message = self.chat_state.find_message_with_button(self.chat_id, button_text)
        if message is None:
            raise ButtonNotFoundError(
                f"No button with text '{button_text}' found in chat"
            )

        callback_data = message.get_button_callback_data(button_text)
        if callback_data is None:
            raise ButtonNotFoundError(
                f"Button '{button_text}' found but has no callback_data"
            )

        await self.click_button(callback_data, message.message_id)

    async def click_button_at(self, row: int, col: int, message_id: int | None = None) -> None:
        """Simulate user clicking inline button by position."""
        if message_id is None:
            last_bot_msg = self.chat_state.get_last_bot_message(self.chat_id)
            if last_bot_msg is None:
                raise NoMessagesError("No bot messages in chat to click button on")
            message_id = last_bot_msg.message_id
            message = last_bot_msg
        else:
            message = self.chat_state.get_message(self.chat_id, message_id)
            if message is None:
                raise NoMessagesError(f"Message {message_id} not found")

        button = message.get_button_at(row, col)
        if button is None:
            raise ButtonNotFoundError(
                f"No button at position ({row}, {col}) in message {message_id}"
            )

        callback_data = button.get("callback_data")
        if callback_data is None:
            raise ButtonNotFoundError(
                f"Button at ({row}, {col}) has no callback_data"
            )

        await self.click_button(callback_data, message_id)

    # =========================================================================
    # Stateful Chat Access
    # =========================================================================

    def get_conversation(self, include_deleted: bool = False) -> list[StoredMessage]:
        """Get full conversation history ordered by time."""
        return self.chat_state.get_conversation(self.chat_id, include_deleted)

    def get_bot_messages(self, include_deleted: bool = False) -> list[StoredMessage]:
        """Get all bot messages in conversation."""
        return self.chat_state.get_bot_messages(self.chat_id, include_deleted)

    def get_user_messages(self, include_deleted: bool = False) -> list[StoredMessage]:
        """Get all user messages in conversation."""
        return self.chat_state.get_user_messages(self.chat_id, include_deleted)

    def get_message(self, message_id: int) -> StoredMessage | None:
        """Get specific message by ID."""
        return self.chat_state.get_message(self.chat_id, message_id)

    def get_last_bot_message(self) -> StoredMessage | None:
        """Get the most recent bot message."""
        return self.chat_state.get_last_bot_message(self.chat_id)

    def get_message_count(self, include_deleted: bool = False) -> int:
        """Get total number of messages in chat."""
        return self.chat_state.get_message_count(self.chat_id, include_deleted)

    def get_thread_messages(
        self, chat_id: int, thread_id: int, include_deleted: bool = False
    ) -> list[StoredMessage]:
        """Get messages in a specific forum topic thread."""
        return self.chat_state.get_thread_messages(chat_id, thread_id, include_deleted)

    def get_forum_topic(self, chat_id: int, thread_id: int) -> ForumTopic | None:
        """Get forum topic by chat_id and thread_id."""
        return self.chat_state.get_forum_topic(chat_id, thread_id)

    def get_forum_topics(self, chat_id: int) -> list[ForumTopic]:
        """Get all forum topics for a chat."""
        return self.chat_state.get_forum_topics(chat_id)

    # =========================================================================
    # Legacy Response Inspection (Tracker-based)
    # =========================================================================

    def get_sent_messages(self) -> list[TrackedRequest]:
        """Get all sendMessage requests."""
        return self._server.tracker.get_send_message_requests()

    def get_deleted_messages(self) -> list[TrackedRequest]:
        """Get all deleteMessage requests."""
        return self._server.tracker.get_delete_message_requests()

    def get_edited_messages(self) -> list[TrackedRequest]:
        """Get all editMessageText requests."""
        return self._server.tracker.get_edit_message_text_requests()

    def get_edited_markups(self) -> list[TrackedRequest]:
        """Get all editMessageReplyMarkup requests."""
        return self._server.tracker.get_edit_message_reply_markup_requests()

    def get_callback_answers(self) -> list[TrackedRequest]:
        """Get all answerCallbackQuery requests."""
        return self._server.tracker.get_answer_callback_query_requests()

    def get_all_requests(self) -> list[TrackedRequest]:
        """Get all tracked requests."""
        return self._server.tracker.requests.copy()

    def get_last_message(self) -> TrackedRequest | None:
        """Get the last sendMessage request."""
        messages = self.get_sent_messages()
        return messages[-1] if messages else None

    def get_last_text(self) -> str | None:
        """Get text from the last sent message."""
        last = self.get_last_message()
        if last is None:
            return None
        return last.data.get("text")

    def get_last_keyboard(self) -> dict[str, Any] | None:
        """Get reply_markup from the last sent message."""
        last = self.get_last_message()
        if last is None:
            return None
        return last.data.get("reply_markup")

    # =========================================================================
    # Assertions
    # =========================================================================

    def assert_message_sent(self) -> None:
        """Assert that at least one message was sent."""
        assert self.get_sent_messages(), "No messages were sent"

    def assert_message_contains(self, text: str) -> None:
        """Assert that the last message contains specific text."""
        last_text = self.get_last_text()
        assert last_text is not None, "No message was sent"
        assert text in last_text, f"Text '{text}' not found in message: {last_text}"

    def assert_keyboard_has_button(self, button_text: str) -> None:
        """Assert that the last message has a button with specific text."""
        keyboard = self.get_last_keyboard()
        assert keyboard is not None, "No keyboard in last message"

        if "inline_keyboard" in keyboard:
            for row in keyboard["inline_keyboard"]:
                for button in row:
                    if button_text in button.get("text", ""):
                        return
            raise AssertionError(f"Button '{button_text}' not found in inline keyboard")

        if "keyboard" in keyboard:
            for row in keyboard["keyboard"]:
                for button in row:
                    btn_text = button.get("text", "") if isinstance(button, dict) else str(button)
                    if button_text in btn_text:
                        return
            raise AssertionError(f"Button '{button_text}' not found in reply keyboard")

        raise AssertionError(f"Button '{button_text}' not found in keyboard")

    def assert_callback_answered(self) -> None:
        """Assert that callback query was answered."""
        assert self.get_callback_answers(), "Callback query was not answered"

    def assert_message_deleted(self, message_id: int) -> None:
        """Assert that a specific message was deleted."""
        message = self.get_message(message_id)
        assert message is not None, f"Message {message_id} not found"
        assert message.is_deleted, f"Message {message_id} was not deleted"

    def assert_message_edited(self, message_id: int) -> None:
        """Assert that a specific message was edited."""
        message = self.get_message(message_id)
        assert message is not None, f"Message {message_id} not found"
        assert message.edited_at is not None, f"Message {message_id} was not edited"

    def assert_conversation_length(self, expected: int, include_deleted: bool = False) -> None:
        """Assert the conversation has expected number of messages."""
        actual = self.get_message_count(include_deleted)
        assert actual == expected, f"Expected {expected} messages, got {actual}"

    def assert_last_bot_message_contains(self, text: str) -> None:
        """Assert that the last bot message contains specific text."""
        last = self.get_last_bot_message()
        assert last is not None, "No bot messages in chat"
        assert last.text is not None, "Last bot message has no text"
        assert text in last.text, f"Text '{text}' not found in: {last.text}"

    def assert_last_bot_message_has_button(self, button_text: str) -> None:
        """Assert that the last bot message has a button with specific text."""
        last = self.get_last_bot_message()
        assert last is not None, "No bot messages in chat"
        assert last.has_inline_keyboard(), "Last bot message has no inline keyboard"

        keyboard = last.reply_markup.get("inline_keyboard", [])
        for row in keyboard:
            for button in row:
                if button_text in button.get("text", ""):
                    return
        raise AssertionError(f"Button '{button_text}' not found in last bot message keyboard")

    def assert_forum_topic_created(self, chat_id: int, name: str) -> ForumTopic:
        """Assert a forum topic was created with given name."""
        topics = self.get_forum_topics(chat_id)
        for topic in topics:
            if topic.name == name:
                return topic
        raise AssertionError(f"Forum topic '{name}' not found in chat {chat_id}")

    def assert_forum_topic_closed(self, chat_id: int, thread_id: int) -> None:
        """Assert a forum topic is closed."""
        topic = self.get_forum_topic(chat_id, thread_id)
        assert topic is not None, f"Forum topic {thread_id} not found in chat {chat_id}"
        assert topic.is_closed, f"Forum topic {thread_id} is not closed"

    def assert_forum_topic_icon(self, chat_id: int, thread_id: int, icon_id: str) -> None:
        """Assert a forum topic has specific icon."""
        topic = self.get_forum_topic(chat_id, thread_id)
        assert topic is not None, f"Forum topic {thread_id} not found in chat {chat_id}"
        assert topic.icon_custom_emoji_id == icon_id, (
            f"Expected icon {icon_id}, got {topic.icon_custom_emoji_id}"
        )

    # =========================================================================
    # Utilities
    # =========================================================================

    def clear(self) -> None:
        """Clear all tracked requests, chat state, and reset update builder."""
        self._server.clear()
        self._update_builder.reset()
        logger.debug("Cleared all state")

    def clear_requests_only(self) -> None:
        """Clear only tracked requests, keep chat state."""
        self._server.tracker.clear_requests_only()
