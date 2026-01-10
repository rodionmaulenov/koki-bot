"""Тесты для middleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.middleware import SaveCommandsMessageMiddleware
from app.config import get_settings


class TestSaveCommandsMessageMiddleware:
    """Тесты для SaveCommandsMessageMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Создаёт экземпляр middleware."""
        return SaveCommandsMessageMiddleware()

    @pytest.fixture
    def mock_handler(self):
        """Mock handler который вызывается после middleware."""
        return AsyncMock(return_value="handler_result")

    @pytest.fixture
    def mock_commands_service(self):
        """Mock CommandsMessagesService."""
        service = MagicMock()
        service.add = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_saves_message_in_commands_topic(
        self,
        middleware,
        mock_handler,
        mock_commands_service,
        mock_message,
    ):
        """Сохраняет message_id для сообщений в топике Команды."""
        settings = get_settings()

        message = mock_message(
            text="test",
            user_id=123,
            chat_id=settings.commands_group_id,
            message_id=12345,
            message_thread_id=settings.commands_thread_id,
        )

        data = {"commands_messages_service": mock_commands_service}

        result = await middleware(mock_handler, message, data)

        # message_id сохранён
        mock_commands_service.add.assert_called_once_with(12345)
        # handler вызван
        mock_handler.assert_called_once_with(message, data)
        assert result == "handler_result"

    @pytest.mark.asyncio
    async def test_skips_other_chats(
        self,
        middleware,
        mock_handler,
        mock_commands_service,
        mock_message,
    ):
        """Не сохраняет сообщения из других чатов."""
        message = mock_message(
            text="test",
            user_id=123,
            chat_id=999999999,  # Другой чат
            message_id=12345,
            message_thread_id=1,
        )

        data = {"commands_messages_service": mock_commands_service}

        await middleware(mock_handler, message, data)

        # message_id НЕ сохранён
        mock_commands_service.add.assert_not_called()
        # handler всё равно вызван
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_other_topics(
        self,
        middleware,
        mock_handler,
        mock_commands_service,
        mock_message,
    ):
        """Не сохраняет сообщения из других топиков."""
        settings = get_settings()

        message = mock_message(
            text="test",
            user_id=123,
            chat_id=settings.commands_group_id,
            message_id=12345,
            message_thread_id=99999,  # Другой топик
        )

        data = {"commands_messages_service": mock_commands_service}

        await middleware(mock_handler, message, data)

        # message_id НЕ сохранён
        mock_commands_service.add.assert_not_called()
        # handler вызван
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_missing_service(
        self,
        middleware,
        mock_handler,
        mock_message,
    ):
        """Работает если сервис не передан."""
        settings = get_settings()

        message = mock_message(
            text="test",
            user_id=123,
            chat_id=settings.commands_group_id,
            message_id=12345,
            message_thread_id=settings.commands_thread_id,
        )

        data = {}  # Нет сервиса

        # Не должно упасть
        await middleware(mock_handler, message, data)

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_service_error(
        self,
        middleware,
        mock_handler,
        mock_message,
    ):
        """Продолжает работу при ошибке сервиса."""
        settings = get_settings()

        message = mock_message(
            text="test",
            user_id=123,
            chat_id=settings.commands_group_id,
            message_id=12345,
            message_thread_id=settings.commands_thread_id,
        )

        # Сервис бросает ошибку
        mock_service = MagicMock()
        mock_service.add = AsyncMock(side_effect=Exception("DB error"))

        data = {"commands_messages_service": mock_service}

        # Не должно упасть
        await middleware(mock_handler, message, data)

        # handler всё равно вызван
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_through_handler_result(
        self,
        middleware,
        mock_commands_service,
        mock_message,
    ):
        """Возвращает результат handler."""
        settings = get_settings()

        message = mock_message(
            text="test",
            user_id=123,
            chat_id=settings.commands_group_id,
            message_id=12345,
            message_thread_id=settings.commands_thread_id,
        )

        expected_result = {"some": "data"}
        handler = AsyncMock(return_value=expected_result)

        data = {"commands_messages_service": mock_commands_service}

        result = await middleware(handler, message, data)

        assert result == expected_result