import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from redis.asyncio import Redis

from repositories.commands_messages_repository import CommandsMessagesRepository
from repositories.manager_repository import ManagerRepository
from topic_access.access import has_access

logger = logging.getLogger(__name__)

AUTO_DELETE_DELAY = 7
ADD_ACTIVE_KEY_PREFIX = "kok:add_active"


class MessageMiddleware(BaseMiddleware):
    def __init__(
        self,
        thread_id: int,
        repository: CommandsMessagesRepository,
        manager_repository: ManagerRepository,
        redis: Redis,
        access_denied_text: str = "🚫 У вас нет доступа",
    ) -> None:
        self._thread_id = thread_id
        self._repository = repository
        self._manager_repository = manager_repository
        self._redis = redis
        self._access_denied_text = access_denied_text

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if event.message_thread_id != self._thread_id:
            return await handler(event, data)

        if not event.from_user:
            return None

        if await has_access(event.from_user.id, self._manager_repository):
            if await self._is_blocked_by_active_flow(event.from_user.id):
                try:
                    await event.delete()
                except TelegramBadRequest:
                    pass
                return None

            try:
                await self._repository.add_message(event.message_id)
            except Exception:
                logger.warning("Failed to track message %d", event.message_id)
            return await handler(event, data)

        logger.warning("Access denied for user_id=%d", event.from_user.id)
        reply = await event.answer(self._access_denied_text)
        asyncio.create_task(
            self._auto_delete(event.bot, event.chat.id, [event.message_id, reply.message_id]),
        )
        return None

    async def _is_blocked_by_active_flow(self, user_id: int) -> bool:
        try:
            active_id = await self._redis.get(
                f"{ADD_ACTIVE_KEY_PREFIX}:{self._thread_id}",
            )
            if active_id and int(active_id) != user_id:
                return True
        except Exception:
            pass
        return False

    @staticmethod
    async def _auto_delete(bot, chat_id: int, message_ids: list[int]) -> None:
        try:
            await asyncio.sleep(AUTO_DELETE_DELAY)
            for msg_id in message_ids:
                try:
                    await bot.delete_message(chat_id, msg_id)
                except TelegramBadRequest:
                    pass
        except Exception:
            logger.debug("Auto-delete failed for chat_id=%d", chat_id)
