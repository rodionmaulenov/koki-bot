"""
Tests for forum topic API methods.

Verifies that createForumTopic, editForumTopic, closeForumTopic,
reopenForumTopic, and pinChatMessage work correctly through the mock server.
"""
import pytest
from aiogram import Dispatcher

from tests.mock_server import MockBot, MockTelegramBot


GROUP_CHAT_ID = -1001234567890


class TestCreateForumTopic:
    """Test createForumTopic API method."""

    @pytest.mark.asyncio
    async def test_create_forum_topic_returns_topic_object(self) -> None:
        """createForumTopic returns ForumTopic with message_thread_id."""
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name="Test Topic",
            )

            assert topic.message_thread_id > 0
            assert topic.name == "Test Topic"
            assert topic.icon_color > 0

    @pytest.mark.asyncio
    async def test_create_forum_topic_with_icon(self) -> None:
        """createForumTopic with custom emoji icon."""
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name="With Icon",
                icon_custom_emoji_id="5368324170671202286",
            )

            assert topic.message_thread_id > 0
            assert topic.name == "With Icon"

    @pytest.mark.asyncio
    async def test_create_forum_topic_tracked_in_chat_state(self) -> None:
        """Created topic is stored in ChatState."""
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name="Tracked Topic",
            )

            stored = mock.chat_state.get_forum_topic(
                GROUP_CHAT_ID, topic.message_thread_id,
            )
            assert stored is not None
            assert stored.name == "Tracked Topic"
            assert not stored.is_closed

    @pytest.mark.asyncio
    async def test_create_multiple_topics(self) -> None:
        """Multiple topics get unique thread IDs."""
        async with MockBot() as mock:
            topic1 = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Topic 1",
            )
            topic2 = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Topic 2",
            )

            assert topic1.message_thread_id != topic2.message_thread_id

    @pytest.mark.asyncio
    async def test_create_forum_topic_request_tracked(self) -> None:
        """createForumTopic request is tracked by RequestTracker."""
        async with MockBot() as mock:
            await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Tracked",
            )

            requests = mock.tracker.get_create_forum_topic_requests()
            assert len(requests) == 1
            assert requests[0].data.get("name") == "Tracked"


class TestEditForumTopic:
    """Test editForumTopic API method."""

    @pytest.mark.asyncio
    async def test_edit_forum_topic_name(self) -> None:
        """editForumTopic changes topic name in ChatState."""
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Original",
            )

            result = await mock.bot.edit_forum_topic(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic.message_thread_id,
                name="Renamed",
            )
            assert result is True

            stored = mock.chat_state.get_forum_topic(
                GROUP_CHAT_ID, topic.message_thread_id,
            )
            assert stored.name == "Renamed"

    @pytest.mark.asyncio
    async def test_edit_forum_topic_icon(self) -> None:
        """editForumTopic changes topic icon in ChatState."""
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Test",
            )

            # Change icon (like workers do for refused courses)
            await mock.bot.edit_forum_topic(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic.message_thread_id,
                icon_custom_emoji_id="5379748062124056162",
            )

            stored = mock.chat_state.get_forum_topic(
                GROUP_CHAT_ID, topic.message_thread_id,
            )
            assert stored.icon_custom_emoji_id == "5379748062124056162"

    @pytest.mark.asyncio
    async def test_edit_forum_topic_tracked(self) -> None:
        """editForumTopic request is tracked."""
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Test",
            )

            await mock.bot.edit_forum_topic(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic.message_thread_id,
                name="Edited",
            )

            requests = mock.tracker.get_edit_forum_topic_requests()
            assert len(requests) == 1


class TestCloseForumTopic:
    """Test closeForumTopic API method."""

    @pytest.mark.asyncio
    async def test_close_forum_topic(self) -> None:
        """closeForumTopic marks topic as closed in ChatState."""
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Close Me",
            )

            result = await mock.bot.close_forum_topic(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic.message_thread_id,
            )
            assert result is True

            stored = mock.chat_state.get_forum_topic(
                GROUP_CHAT_ID, topic.message_thread_id,
            )
            assert stored.is_closed

    @pytest.mark.asyncio
    async def test_close_forum_topic_tracked(self) -> None:
        """closeForumTopic request is tracked."""
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Test",
            )

            await mock.bot.close_forum_topic(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic.message_thread_id,
            )

            requests = mock.tracker.get_close_forum_topic_requests()
            assert len(requests) == 1


class TestReopenForumTopic:
    """Test reopenForumTopic API method."""

    @pytest.mark.asyncio
    async def test_reopen_forum_topic(self) -> None:
        """reopenForumTopic marks topic as open in ChatState."""
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Reopen Me",
            )
            await mock.bot.close_forum_topic(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic.message_thread_id,
            )

            result = await mock.bot.reopen_forum_topic(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic.message_thread_id,
            )
            assert result is True

            stored = mock.chat_state.get_forum_topic(
                GROUP_CHAT_ID, topic.message_thread_id,
            )
            assert not stored.is_closed


class TestPinChatMessage:
    """Test pinChatMessage API method."""

    @pytest.mark.asyncio
    async def test_pin_chat_message(self) -> None:
        """pinChatMessage marks message as pinned in ChatState."""
        async with MockBot() as mock:
            msg = await mock.bot.send_message(chat_id=123, text="Pin me")

            result = await mock.bot.pin_chat_message(
                chat_id=123,
                message_id=msg.message_id,
            )
            assert result is True

            stored = mock.chat_state.get_message(123, msg.message_id)
            assert stored.is_pinned

    @pytest.mark.asyncio
    async def test_pin_chat_message_tracked(self) -> None:
        """pinChatMessage request is tracked."""
        async with MockBot() as mock:
            msg = await mock.bot.send_message(chat_id=123, text="Pin me")

            await mock.bot.pin_chat_message(
                chat_id=123,
                message_id=msg.message_id,
            )

            requests = mock.tracker.get_pin_chat_message_requests()
            assert len(requests) == 1


class TestForumTopicAssertions:
    """Test forum topic assertion helpers on MockTelegramBot."""

    @pytest.mark.asyncio
    async def test_assert_forum_topic_created(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test assert_forum_topic_created passes."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            await mock_bot.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="My Topic",
            )

            topic = mock_bot.assert_forum_topic_created(GROUP_CHAT_ID, "My Topic")
            assert topic.message_thread_id > 0

    @pytest.mark.asyncio
    async def test_assert_forum_topic_created_fails(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test assert_forum_topic_created fails when topic doesn't exist."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            with pytest.raises(AssertionError, match="not found"):
                mock_bot.assert_forum_topic_created(GROUP_CHAT_ID, "Missing")

    @pytest.mark.asyncio
    async def test_assert_forum_topic_closed(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test assert_forum_topic_closed passes."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            topic = await mock_bot.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Close Me",
            )
            await mock_bot.bot.close_forum_topic(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic.message_thread_id,
            )

            mock_bot.assert_forum_topic_closed(
                GROUP_CHAT_ID, topic.message_thread_id,
            )

    @pytest.mark.asyncio
    async def test_assert_forum_topic_icon(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test assert_forum_topic_icon passes."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            topic = await mock_bot.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID, name="Iconized",
            )
            await mock_bot.bot.edit_forum_topic(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic.message_thread_id,
                icon_custom_emoji_id="12345",
            )

            mock_bot.assert_forum_topic_icon(
                GROUP_CHAT_ID, topic.message_thread_id, "12345",
            )
