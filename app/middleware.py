"""Middleware для бота."""

from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from app.config import get_settings

settings = get_settings()


class SaveCommandsMessageMiddleware(BaseMiddleware):
    """Сохраняет message_id всех сообщений в топике Команды."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        # Проверяем что это сообщение в топике "Команды"
        if (
            event.chat.id == settings.manager_group_id
            and event.message_thread_id == settings.commands_thread_id
        ):
            # Сохраняем message_id
            commands_messages_service = data.get("commands_messages_service")
            if commands_messages_service:
                try:
                    await commands_messages_service.add(event.message_id)
                except Exception:
                    pass  # Игнорируем ошибки сохранения

        # Продолжаем обработку
        return await handler(event, data)