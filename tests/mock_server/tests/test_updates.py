"""
Tests for UpdateBuilder — creates aiogram Update objects for testing.
"""
from tests.mock_server.updates import UpdateBuilder


class TestUpdateBuilderMessages:
    """Test message update creation."""

    def test_make_message_update(self) -> None:
        """Create basic text message update."""
        builder = UpdateBuilder(user_id=111, chat_id=111)
        update = builder.make_message_update("Hello")

        assert update.message is not None
        assert update.message.text == "Hello"
        assert update.message.from_user.id == 111
        assert update.message.chat.id == 111
        assert update.message.chat.type == "private"

    def test_make_message_update_supergroup(self) -> None:
        """Create message update for supergroup chat."""
        builder = UpdateBuilder(
            user_id=111, chat_id=-100, chat_type="supergroup",
        )
        update = builder.make_message_update("Group message")

        assert update.message.chat.type == "supergroup"
        assert update.message.chat.id == -100

    def test_make_message_update_with_thread_id(self) -> None:
        """Create message update with message_thread_id."""
        builder = UpdateBuilder(
            user_id=111, chat_id=-100, chat_type="supergroup",
            message_thread_id=42,
        )
        update = builder.make_message_update("In topic")

        assert update.message.message_thread_id == 42

    def test_message_ids_increment(self) -> None:
        """Message IDs increment for each update."""
        builder = UpdateBuilder()
        u1 = builder.make_message_update("First")
        u2 = builder.make_message_update("Second")

        assert u1.message.message_id < u2.message.message_id

    def test_update_ids_increment(self) -> None:
        """Update IDs increment for each update."""
        builder = UpdateBuilder()
        u1 = builder.make_message_update("First")
        u2 = builder.make_message_update("Second")

        assert u1.update_id < u2.update_id


class TestUpdateBuilderMedia:
    """Test media update creation."""

    def test_make_video_update(self) -> None:
        """Create video message update."""
        builder = UpdateBuilder(user_id=111, chat_id=111)
        update = builder.make_video_update(file_id="vid_123", duration=15)

        assert update.message.video is not None
        assert update.message.video.file_id == "vid_123"
        assert update.message.video.duration == 15

    def test_make_video_note_update(self) -> None:
        """Create video note (round video) message update."""
        builder = UpdateBuilder(user_id=111, chat_id=111)
        update = builder.make_video_note_update(file_id="vnote_123", duration=10)

        assert update.message.video_note is not None
        assert update.message.video_note.file_id == "vnote_123"
        assert update.message.video_note.duration == 10

    def test_make_photo_update(self) -> None:
        """Create photo message update."""
        builder = UpdateBuilder(user_id=111, chat_id=111)
        update = builder.make_photo_update(file_id="photo_123", caption="My photo")

        assert update.message.photo is not None
        assert len(update.message.photo) == 2
        assert update.message.caption == "My photo"

    def test_make_document_update(self) -> None:
        """Create document message update."""
        builder = UpdateBuilder(user_id=111, chat_id=111)
        update = builder.make_document_update(
            file_id="doc_123", file_name="test.pdf",
        )

        assert update.message.document is not None
        assert update.message.document.file_name == "test.pdf"

    def test_make_contact_update(self) -> None:
        """Create contact message update."""
        builder = UpdateBuilder(user_id=111, chat_id=111)
        update = builder.make_contact_update(
            phone_number="+998901234567",
            first_name="Test",
        )

        assert update.message.contact is not None
        assert update.message.contact.phone_number == "+998901234567"


class TestUpdateBuilderCallbacks:
    """Test callback query update creation."""

    def test_make_callback_update(self) -> None:
        """Create callback query update."""
        builder = UpdateBuilder(user_id=111, chat_id=111)
        update = builder.make_callback_update(
            callback_data="action:123",
            message_id=50,
        )

        assert update.callback_query is not None
        assert update.callback_query.data == "action:123"
        assert update.callback_query.message.message_id == 50
        assert update.callback_query.from_user.id == 111

    def test_make_callback_update_auto_message_id(self) -> None:
        """Callback update auto-generates message_id if not specified."""
        builder = UpdateBuilder(user_id=111, chat_id=111)
        update = builder.make_callback_update(callback_data="click")

        assert update.callback_query.message.message_id > 0


class TestUpdateBuilderReset:
    """Test reset functionality."""

    def test_reset_counters(self) -> None:
        """Reset sets counters back to 0."""
        builder = UpdateBuilder()
        builder.make_message_update("First")
        builder.make_message_update("Second")

        assert builder.get_last_message_id() == 2

        builder.reset()

        assert builder.get_last_message_id() == 0
        update = builder.make_message_update("After reset")
        assert update.message.message_id == 1
