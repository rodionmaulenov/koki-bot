"""
Tests to verify the mock Telegram server works correctly.
"""
import pytest
from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest

from tests.mock_server import MockTelegramBot


class TestMockServerBasics:
    """Test basic mock server functionality."""

    @pytest.mark.asyncio
    async def test_mock_server_starts_and_stops(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test that mock server can start and stop without errors."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            assert mock_bot.bot is not None
            assert mock_bot._test_server is not None

    @pytest.mark.asyncio
    async def test_send_message_tracked(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test that sending a message is tracked."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            await mock_bot.bot.send_message(chat_id=123, text="Hello")

            messages = mock_bot.get_sent_messages()
            assert len(messages) == 1
            assert messages[0].data.get("text") == "Hello"
            assert str(messages[0].data.get("chat_id")) == "123"

    @pytest.mark.asyncio
    async def test_multiple_messages_tracked(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test that multiple messages are tracked in order."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            await mock_bot.bot.send_message(chat_id=123, text="First")
            await mock_bot.bot.send_message(chat_id=123, text="Second")
            await mock_bot.bot.send_message(chat_id=123, text="Third")

            messages = mock_bot.get_sent_messages()
            assert len(messages) == 3
            assert messages[0].data.get("text") == "First"
            assert messages[1].data.get("text") == "Second"
            assert messages[2].data.get("text") == "Third"

    @pytest.mark.asyncio
    async def test_get_last_text(self, simple_dispatcher: Dispatcher) -> None:
        """Test get_last_text helper method."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            await mock_bot.bot.send_message(chat_id=123, text="First")
            await mock_bot.bot.send_message(chat_id=123, text="Last message")

            assert mock_bot.get_last_text() == "Last message"

    @pytest.mark.asyncio
    async def test_clear_resets_tracking(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test that clear() resets all tracked requests."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            await mock_bot.bot.send_message(chat_id=123, text="Message")
            assert len(mock_bot.get_sent_messages()) == 1

            mock_bot.clear()

            assert len(mock_bot.get_sent_messages()) == 0
            assert mock_bot.get_last_text() is None


class TestMockServerErrorHandling:
    """Test error handling in mock server."""

    @pytest.mark.asyncio
    async def test_send_message_without_chat_id_returns_error(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test that sendMessage without chat_id returns proper error."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            from aiohttp import ClientSession

            server_url = f"http://{mock_bot._test_server.host}:{mock_bot._test_server.port}"
            async with ClientSession() as session:
                async with session.post(
                    f"{server_url}/bot123:token/sendMessage",
                    json={"text": "Hello"},
                ) as response:
                    data = await response.json()
                    assert data["ok"] is False
                    assert data["error_code"] == 400
                    assert "chat_id" in data["description"]

    @pytest.mark.asyncio
    async def test_unknown_method_returns_error(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test that unknown API method returns proper error."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            from aiohttp import ClientSession

            server_url = f"http://{mock_bot._test_server.host}:{mock_bot._test_server.port}"
            async with ClientSession() as session:
                async with session.post(
                    f"{server_url}/bot123:token/unknownMethod",
                    json={},
                ) as response:
                    data = await response.json()
                    assert data["ok"] is False
                    assert data["error_code"] == 404
                    assert "not implemented" in data["description"]


class TestMockServerHttpStatusCodes:
    """Test HTTP status code behavior for aiogram exception mapping."""

    @pytest.mark.asyncio
    async def test_successful_response_returns_http_200(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Successful API calls return HTTP 200."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            from aiohttp import ClientSession

            server_url = f"http://{mock_bot._test_server.host}:{mock_bot._test_server.port}"
            async with ClientSession() as session:
                async with session.post(
                    f"{server_url}/bot123:token/sendMessage",
                    json={"chat_id": 123, "text": "Hello"},
                ) as response:
                    assert response.status == 200
                    data = await response.json()
                    assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_edit_deleted_message_raises_telegram_bad_request(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Editing deleted message raises TelegramBadRequest."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            msg = await mock_bot.bot.send_message(chat_id=123, text="Test")
            mock_bot.chat_state.delete_message(123, msg.message_id)

            with pytest.raises(TelegramBadRequest) as exc_info:
                await mock_bot.bot.edit_message_text(
                    chat_id=123,
                    message_id=msg.message_id,
                    text="Edited",
                )

            assert "deleted" in exc_info.value.message


class TestSendMediaGroup:
    """Test sendMediaGroup mock implementation."""

    @pytest.mark.asyncio
    async def test_send_media_group_returns_messages(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """sendMediaGroup with 3 photos returns 3 Message objects."""
        from aiogram.types import InputMediaPhoto

        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            media = [
                InputMediaPhoto(media="photo_1", caption="Caption text"),
                InputMediaPhoto(media="photo_2"),
                InputMediaPhoto(media="photo_3"),
            ]
            result = await mock_bot.bot.send_media_group(
                chat_id=123, media=media,
            )

            assert len(result) == 3
            assert result[0].caption == "Caption text"
            assert result[1].caption is None

    @pytest.mark.asyncio
    async def test_send_media_group_tracked(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """sendMediaGroup request is tracked."""
        from aiogram.types import InputMediaPhoto

        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            media = [
                InputMediaPhoto(media="photo_a"),
                InputMediaPhoto(media="photo_b"),
            ]
            await mock_bot.bot.send_media_group(chat_id=123, media=media)

            tracked = mock_bot._server.tracker.get_send_media_group_requests()
            assert len(tracked) == 1

    @pytest.mark.asyncio
    async def test_send_media_group_has_media_group_id(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """All returned messages share the same media_group_id."""
        from aiogram.types import InputMediaPhoto

        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            media = [
                InputMediaPhoto(media="p1"),
                InputMediaPhoto(media="p2"),
            ]
            result = await mock_bot.bot.send_media_group(
                chat_id=123, media=media,
            )

            ids = {m.media_group_id for m in result}
            assert len(ids) == 1
            assert None not in ids


class TestMockServerAssertions:
    """Test assertion helper methods."""

    @pytest.mark.asyncio
    async def test_assert_message_sent_passes(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test assert_message_sent passes when message was sent."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            await mock_bot.bot.send_message(chat_id=123, text="Hello")
            mock_bot.assert_message_sent()

    @pytest.mark.asyncio
    async def test_assert_message_sent_fails(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test assert_message_sent fails when no message was sent."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            with pytest.raises(AssertionError, match="No messages were sent"):
                mock_bot.assert_message_sent()

    @pytest.mark.asyncio
    async def test_assert_message_contains(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test assert_message_contains passes when text is present."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            await mock_bot.bot.send_message(chat_id=123, text="Hello World!")
            mock_bot.assert_message_contains("World")

    @pytest.mark.asyncio
    async def test_assert_message_contains_fails(
        self, simple_dispatcher: Dispatcher
    ) -> None:
        """Test assert_message_contains fails when text is missing."""
        async with MockTelegramBot(simple_dispatcher) as mock_bot:
            await mock_bot.bot.send_message(chat_id=123, text="Hello")
            with pytest.raises(AssertionError, match="not found"):
                mock_bot.assert_message_contains("Goodbye")
