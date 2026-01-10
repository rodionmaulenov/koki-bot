"""Middleware для бота."""

import logging
from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class SaveCommandsMessageMiddleware(BaseMiddleware):
    """Сохраняет message_id всех сообщений в топике Команды."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        # Логируем ВСЕ сообщения для отладки
        logger.info(
            f"📨 ANY MSG: chat_id={event.chat.id}, "
            f"thread_id={event.message_thread_id}, "
            f"msg_id={event.message_id}, "
            f"text='{event.text or 'no text'}'"
        )

        # Логируем сообщения из группы команд для отладки
        if event.chat.id == settings.commands_group_id:
            logger.info(
                f"📋 CONFIG: general_thread={settings.general_thread_id}, "
                f"commands_thread={settings.commands_thread_id}"
            )

        # Проверяем что это сообщение в топике "Команды"
        if (
            event.chat.id == settings.commands_group_id
            and event.message_thread_id == settings.commands_thread_id
        ):
            logger.info(f"✅ Message matches commands topic!")
            # Сохраняем message_id пользователя
            commands_messages_service = data.get("commands_messages_service")
            if commands_messages_service:
                try:
                    await commands_messages_service.add(event.message_id)
                    logger.info(f"💾 Saved message_id={event.message_id}")
                except Exception as e:
                    logger.warning(f"Failed to save user message_id: {e}")
            else:
                logger.warning("⚠️ commands_messages_service not found in data!")
        else:
            logger.debug(f"⏭️ Message not in commands topic, skipping")

        # Продолжаем обработку
        return await handler(event, data)