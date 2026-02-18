import logging
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import (
    EditMessageCaption,
    EditMessageMedia,
    EditMessageReplyMarkup,
    EditMessageText,
    TelegramMethod,
)
from aiogram.types import Message

from repositories.commands_messages_repository import CommandsMessagesRepository

logger = logging.getLogger(__name__)

EDIT_METHODS = (
    EditMessageText,
    EditMessageReplyMarkup,
    EditMessageCaption,
    EditMessageMedia,
)


class TrackedBot(Bot):
    def __init__(
        self,
        token: str,
        repository: CommandsMessagesRepository,
        thread_id: int,
        chat_id: int,
        default: DefaultBotProperties | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(token=token, default=default, **kwargs)
        self._repository = repository
        self._thread_id = thread_id
        self._chat_id = chat_id
        self._menu_message_pending = False

    async def send_menu_message(
        self,
        chat_id: int | str,
        text: str,
        **kwargs: Any,
    ) -> Message:
        self._menu_message_pending = True
        return await self.send_message(chat_id=chat_id, text=text, **kwargs)

    async def __call__(
        self,
        method: TelegramMethod[Any],
        request_timeout: int | None = None,
    ) -> Any:
        result = await super().__call__(method, request_timeout=request_timeout)

        if isinstance(method, EDIT_METHODS):
            return result

        if isinstance(result, Message):
            is_menu = self._menu_message_pending
            self._menu_message_pending = False
            await self._track_message(result, is_menu=is_menu)

        return result

    async def untrack_message(self, message_id: int) -> None:
        try:
            await self._repository.delete_by_message_id(message_id)
        except Exception as e:
            logger.debug("Failed to untrack message %d: %s", message_id, e)

    async def _track_message(self, message: Message, is_menu: bool) -> None:
        if message.chat.id != self._chat_id:
            return
        thread_id = message.message_thread_id or 0
        if thread_id != self._thread_id:
            return
        try:
            await self._repository.add_message(
                message_id=message.message_id,
                is_menu=is_menu,
            )
            logger.debug(
                "Tracked message_id=%d is_menu=%s",
                message.message_id,
                is_menu,
            )
        except Exception as e:
            logger.error("Failed to track message %d: %s", message.message_id, e)
