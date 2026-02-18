"""
Tests for ChatState — stateful message and forum topic tracking.
"""
import pytest

from tests.mock_server.chat_state import ChatState


class TestChatStateMessages:
    """Test message storage and retrieval."""

    def test_add_message(self) -> None:
        """Test adding a message to chat."""
        cs = ChatState()
        msg = cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="Hello")

        assert msg.chat_id == 123
        assert msg.from_user_id == 456
        assert msg.text == "Hello"
        assert not msg.is_bot
        assert not msg.is_deleted

    def test_add_bot_message(self) -> None:
        """Test adding a bot message."""
        cs = ChatState()
        msg = cs.add_message(chat_id=123, from_user_id=1234567890, is_bot=True, text="Bot reply")

        assert msg.is_bot
        assert msg.text == "Bot reply"

    def test_get_conversation_ordered(self) -> None:
        """Test conversation returns messages in order."""
        cs = ChatState()
        cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="First")
        cs.add_message(chat_id=123, from_user_id=789, is_bot=True, text="Second")
        cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="Third")

        conv = cs.get_conversation(123)
        assert len(conv) == 3
        assert conv[0].text == "First"
        assert conv[1].text == "Second"
        assert conv[2].text == "Third"

    def test_get_bot_messages(self) -> None:
        """Test filtering bot messages."""
        cs = ChatState()
        cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="User")
        cs.add_message(chat_id=123, from_user_id=789, is_bot=True, text="Bot1")
        cs.add_message(chat_id=123, from_user_id=789, is_bot=True, text="Bot2")

        bot_msgs = cs.get_bot_messages(123)
        assert len(bot_msgs) == 2
        assert bot_msgs[0].text == "Bot1"
        assert bot_msgs[1].text == "Bot2"

    def test_get_user_messages(self) -> None:
        """Test filtering user messages."""
        cs = ChatState()
        cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="User1")
        cs.add_message(chat_id=123, from_user_id=789, is_bot=True, text="Bot")
        cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="User2")

        user_msgs = cs.get_user_messages(123)
        assert len(user_msgs) == 2
        assert user_msgs[0].text == "User1"

    def test_delete_message(self) -> None:
        """Test deleting a message."""
        cs = ChatState()
        msg = cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="Delete me")

        result = cs.delete_message(123, msg.message_id)
        assert result is True

        conv = cs.get_conversation(123)
        assert len(conv) == 0

        conv_with_deleted = cs.get_conversation(123, include_deleted=True)
        assert len(conv_with_deleted) == 1
        assert conv_with_deleted[0].is_deleted

    def test_delete_nonexistent_message(self) -> None:
        """Test deleting non-existent message returns False."""
        cs = ChatState()
        result = cs.delete_message(123, 999)
        assert result is False

    def test_edit_message_text(self) -> None:
        """Test editing message text."""
        cs = ChatState()
        msg = cs.add_message(chat_id=123, from_user_id=789, is_bot=True, text="Original")

        edited = cs.edit_message_text(123, msg.message_id, "Edited")
        assert edited is not None
        assert edited.text == "Edited"
        assert edited.edited_at is not None

    def test_edit_deleted_message_returns_none(self) -> None:
        """Test editing deleted message returns None."""
        cs = ChatState()
        msg = cs.add_message(chat_id=123, from_user_id=789, is_bot=True, text="Original")
        cs.delete_message(123, msg.message_id)

        result = cs.edit_message_text(123, msg.message_id, "Edited")
        assert result is None

    def test_edit_message_reply_markup(self) -> None:
        """Test editing message reply markup."""
        cs = ChatState()
        markup = {"inline_keyboard": [[{"text": "Old", "callback_data": "old"}]]}
        msg = cs.add_message(
            chat_id=123, from_user_id=789, is_bot=True,
            text="With buttons", reply_markup=markup,
        )

        new_markup = {"inline_keyboard": [[{"text": "New", "callback_data": "new"}]]}
        edited = cs.edit_message_reply_markup(123, msg.message_id, new_markup)

        assert edited is not None
        assert edited.reply_markup == new_markup

    def test_pin_message(self) -> None:
        """Test pinning a message."""
        cs = ChatState()
        msg = cs.add_message(chat_id=123, from_user_id=789, is_bot=True, text="Pin me")

        result = cs.pin_message(123, msg.message_id)
        assert result is True
        assert msg.is_pinned

    def test_pin_nonexistent_message(self) -> None:
        """Test pinning non-existent message returns False."""
        cs = ChatState()
        result = cs.pin_message(123, 999)
        assert result is False

    def test_message_thread_id(self) -> None:
        """Test messages with thread_id (forum topics)."""
        cs = ChatState()
        cs.add_message(
            chat_id=-100, from_user_id=789, is_bot=True,
            text="In topic", message_thread_id=42,
        )
        cs.add_message(
            chat_id=-100, from_user_id=789, is_bot=True,
            text="Not in topic",
        )

        thread_msgs = cs.get_thread_messages(-100, 42)
        assert len(thread_msgs) == 1
        assert thread_msgs[0].text == "In topic"

    def test_get_last_bot_message(self) -> None:
        """Test getting last bot message."""
        cs = ChatState()
        cs.add_message(chat_id=123, from_user_id=789, is_bot=True, text="First bot")
        cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="User")
        cs.add_message(chat_id=123, from_user_id=789, is_bot=True, text="Last bot")

        last = cs.get_last_bot_message(123)
        assert last is not None
        assert last.text == "Last bot"

    def test_get_last_bot_message_empty(self) -> None:
        """Test getting last bot message when none exist."""
        cs = ChatState()
        assert cs.get_last_bot_message(123) is None

    def test_clear_specific_chat(self) -> None:
        """Test clearing a specific chat."""
        cs = ChatState()
        cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="Chat 123")
        cs.add_message(chat_id=456, from_user_id=789, is_bot=False, text="Chat 456")

        cs.clear(123)

        assert cs.get_message_count(123) == 0
        assert cs.get_message_count(456) == 1

    def test_clear_all(self) -> None:
        """Test clearing all chats."""
        cs = ChatState()
        cs.add_message(chat_id=123, from_user_id=456, is_bot=False, text="Chat 123")
        cs.add_message(chat_id=456, from_user_id=789, is_bot=False, text="Chat 456")

        cs.clear()

        assert cs.get_message_count(123) == 0
        assert cs.get_message_count(456) == 0


class TestChatStateForumTopics:
    """Test forum topic storage and operations."""

    def test_create_forum_topic(self) -> None:
        """Test creating a forum topic."""
        cs = ChatState()
        topic = cs.create_forum_topic(chat_id=-100, name="Test Topic")

        assert topic.message_thread_id > 0
        assert topic.chat_id == -100
        assert topic.name == "Test Topic"
        assert topic.icon_color == 7322096
        assert not topic.is_closed

    def test_create_forum_topic_with_icon(self) -> None:
        """Test creating a forum topic with custom icon."""
        cs = ChatState()
        topic = cs.create_forum_topic(
            chat_id=-100, name="With Icon",
            icon_custom_emoji_id="5368324170671202286",
        )

        assert topic.icon_custom_emoji_id == "5368324170671202286"

    def test_get_forum_topic(self) -> None:
        """Test retrieving a forum topic."""
        cs = ChatState()
        created = cs.create_forum_topic(chat_id=-100, name="Find Me")

        found = cs.get_forum_topic(-100, created.message_thread_id)
        assert found is not None
        assert found.name == "Find Me"

    def test_get_nonexistent_forum_topic(self) -> None:
        """Test retrieving non-existent topic returns None."""
        cs = ChatState()
        assert cs.get_forum_topic(-100, 999) is None

    def test_edit_forum_topic_name(self) -> None:
        """Test editing forum topic name."""
        cs = ChatState()
        topic = cs.create_forum_topic(chat_id=-100, name="Original")

        result = cs.edit_forum_topic(-100, topic.message_thread_id, name="Edited")
        assert result is True

        updated = cs.get_forum_topic(-100, topic.message_thread_id)
        assert updated.name == "Edited"

    def test_edit_forum_topic_icon(self) -> None:
        """Test editing forum topic icon."""
        cs = ChatState()
        topic = cs.create_forum_topic(chat_id=-100, name="Test")

        cs.edit_forum_topic(
            -100, topic.message_thread_id,
            icon_custom_emoji_id="5379748062124056162",
        )

        updated = cs.get_forum_topic(-100, topic.message_thread_id)
        assert updated.icon_custom_emoji_id == "5379748062124056162"

    def test_close_forum_topic(self) -> None:
        """Test closing a forum topic."""
        cs = ChatState()
        topic = cs.create_forum_topic(chat_id=-100, name="Close Me")

        result = cs.close_forum_topic(-100, topic.message_thread_id)
        assert result is True

        updated = cs.get_forum_topic(-100, topic.message_thread_id)
        assert updated.is_closed

    def test_reopen_forum_topic(self) -> None:
        """Test reopening a closed forum topic."""
        cs = ChatState()
        topic = cs.create_forum_topic(chat_id=-100, name="Reopen Me")
        cs.close_forum_topic(-100, topic.message_thread_id)

        result = cs.reopen_forum_topic(-100, topic.message_thread_id)
        assert result is True

        updated = cs.get_forum_topic(-100, topic.message_thread_id)
        assert not updated.is_closed

    def test_get_forum_topics(self) -> None:
        """Test getting all forum topics for a chat."""
        cs = ChatState()
        cs.create_forum_topic(chat_id=-100, name="Topic 1")
        cs.create_forum_topic(chat_id=-100, name="Topic 2")
        cs.create_forum_topic(chat_id=-200, name="Other Chat")

        topics = cs.get_forum_topics(-100)
        assert len(topics) == 2
        names = {t.name for t in topics}
        assert names == {"Topic 1", "Topic 2"}

    def test_clear_removes_forum_topics(self) -> None:
        """Test that clear removes forum topics too."""
        cs = ChatState()
        cs.create_forum_topic(chat_id=-100, name="Topic")

        cs.clear()
        assert cs.get_forum_topics(-100) == []

    def test_clear_specific_chat_removes_topics(self) -> None:
        """Test clearing specific chat removes its topics."""
        cs = ChatState()
        cs.create_forum_topic(chat_id=-100, name="Chat 1 Topic")
        cs.create_forum_topic(chat_id=-200, name="Chat 2 Topic")

        cs.clear(-100)
        assert cs.get_forum_topics(-100) == []
        assert len(cs.get_forum_topics(-200)) == 1


class TestStoredMessageButtons:
    """Test button-related StoredMessage methods."""

    def test_has_inline_keyboard(self) -> None:
        """Test inline keyboard detection."""
        cs = ChatState()
        markup = {"inline_keyboard": [[{"text": "Click", "callback_data": "cb"}]]}
        msg = cs.add_message(
            chat_id=123, from_user_id=789, is_bot=True,
            text="Buttons", reply_markup=markup,
        )

        assert msg.has_inline_keyboard()

    def test_no_inline_keyboard(self) -> None:
        """Test message without inline keyboard."""
        cs = ChatState()
        msg = cs.add_message(
            chat_id=123, from_user_id=789, is_bot=True, text="No buttons",
        )

        assert not msg.has_inline_keyboard()

    def test_get_button_callback_data(self) -> None:
        """Test finding button callback data by text."""
        cs = ChatState()
        markup = {"inline_keyboard": [
            [{"text": "Accept", "callback_data": "accept_1"}],
            [{"text": "Reject", "callback_data": "reject_1"}],
        ]}
        msg = cs.add_message(
            chat_id=123, from_user_id=789, is_bot=True,
            text="Choose", reply_markup=markup,
        )

        assert msg.get_button_callback_data("Accept") == "accept_1"
        assert msg.get_button_callback_data("Reject") == "reject_1"
        assert msg.get_button_callback_data("Other") is None

    def test_get_button_at(self) -> None:
        """Test getting button by position."""
        cs = ChatState()
        markup = {"inline_keyboard": [
            [{"text": "A", "callback_data": "a"}, {"text": "B", "callback_data": "b"}],
            [{"text": "C", "callback_data": "c"}],
        ]}
        msg = cs.add_message(
            chat_id=123, from_user_id=789, is_bot=True,
            text="Grid", reply_markup=markup,
        )

        assert msg.get_button_at(0, 0)["text"] == "A"
        assert msg.get_button_at(0, 1)["text"] == "B"
        assert msg.get_button_at(1, 0)["text"] == "C"
        assert msg.get_button_at(2, 0) is None
        assert msg.get_button_at(0, 5) is None

    def test_find_message_with_button(self) -> None:
        """Test finding message containing a specific button."""
        cs = ChatState()
        cs.add_message(
            chat_id=123, from_user_id=789, is_bot=True, text="No buttons",
        )
        markup = {"inline_keyboard": [[{"text": "Special", "callback_data": "special"}]]}
        cs.add_message(
            chat_id=123, from_user_id=789, is_bot=True,
            text="Has button", reply_markup=markup,
        )

        found = cs.find_message_with_button(123, "Special")
        assert found is not None
        assert found.text == "Has button"

    def test_find_message_with_button_returns_newest(self) -> None:
        """Test that find_message_with_button returns the newest matching message."""
        cs = ChatState()
        markup = {"inline_keyboard": [[{"text": "Click", "callback_data": "old"}]]}
        cs.add_message(
            chat_id=123, from_user_id=789, is_bot=True,
            text="Old message", reply_markup=markup,
        )

        markup2 = {"inline_keyboard": [[{"text": "Click", "callback_data": "new"}]]}
        cs.add_message(
            chat_id=123, from_user_id=789, is_bot=True,
            text="New message", reply_markup=markup2,
        )

        found = cs.find_message_with_button(123, "Click")
        assert found is not None
        assert found.text == "New message"
