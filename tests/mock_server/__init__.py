"""
Mock Telegram Server for integration testing.

Provides a fake Telegram Bot API server that accepts requests locally,
eliminating network calls and making tests fast and deterministic.

Includes forum topic support for koki-bot group topic testing.

Usage:
    from tests.mock_server import MockTelegramBot, MockBot

    @pytest.mark.asyncio
    async def test_bot_sends_message():
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(some_router)

        async with MockTelegramBot(dp) as mock_bot:
            await mock_bot.send_message("/start")
            assert "Добро пожаловать" in mock_bot.get_last_text()

    @pytest.mark.asyncio
    async def test_forum_topics():
        async with MockBot() as mock:
            topic = await mock.bot.create_forum_topic(
                chat_id=-1001234567890,
                name="Test Topic",
            )
            assert topic.message_thread_id > 0
"""
from tests.mock_server.chat_state import ChatState, ForumTopic, StoredMessage
from tests.mock_server.client import (
    ButtonNotFoundError,
    MockBot,
    MockTelegramBot,
    NoMessagesError,
)
from tests.mock_server.server import FakeTelegramServer
from tests.mock_server.tracker import RequestTracker, TrackedRequest
from tests.mock_server.updates import UpdateBuilder

__all__ = [
    # Main clients
    "MockTelegramBot",
    "MockBot",
    # Chat state
    "ChatState",
    "StoredMessage",
    "ForumTopic",
    # Exceptions
    "ButtonNotFoundError",
    "NoMessagesError",
    # Server internals (for advanced use)
    "FakeTelegramServer",
    "RequestTracker",
    "TrackedRequest",
    "UpdateBuilder",
]
