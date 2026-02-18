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
