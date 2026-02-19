import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from repositories.manager_repository import ManagerRepository
from topic_access.access import has_access

logger = logging.getLogger(__name__)


class CallbackMiddleware(BaseMiddleware):
    def __init__(
        self,
        thread_id: int,
        manager_repository: ManagerRepository,
        access_denied_toast: str = "🚫 У вас нет доступа",
    ) -> None:
        self._thread_id = thread_id
        self._manager_repository = manager_repository
        self._access_denied_toast = access_denied_toast

    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        if not event.message:
            return await handler(event, data)

        if event.message.message_thread_id != self._thread_id:
            return await handler(event, data)

        if not event.from_user:
            await event.answer(self._access_denied_toast, show_alert=True)
            return None

        if await has_access(event.from_user.id, self._manager_repository):
            return await handler(event, data)

        logger.warning("Callback access denied for user_id=%d", event.from_user.id)
        await event.answer(self._access_denied_toast, show_alert=True)
        return None
