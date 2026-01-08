"""Тесты для handlers/fallback.py."""
import pytest

from app import templates


class TestFallbackHandler:
    """Тесты для fallback_handler."""

    @pytest.mark.asyncio
    async def test_text_message(self, mock_message):
        """Текстовое сообщение → заглушка."""
        from app.handlers.fallback import fallback_handler

        message = mock_message(text="Привет!")

        await fallback_handler(message)

        message.answer.assert_called_once_with(templates.FALLBACK_MESSAGE)

    @pytest.mark.asyncio
    async def test_empty_message(self, mock_message):
        """Пустое сообщение → заглушка."""
        from app.handlers.fallback import fallback_handler

        message = mock_message(text="")

        await fallback_handler(message)

        message.answer.assert_called_once_with(templates.FALLBACK_MESSAGE)