import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from repositories.commands_messages_repository import CommandsMessagesRepository

logger = logging.getLogger(__name__)


class CommandsMessagesService:
    def __init__(
        self,
        bot: Bot,
        repository: CommandsMessagesRepository,
        chat_id: int,
    ) -> None:
        self._bot = bot
        self._repository = repository
        self._chat_id = chat_id

    async def clear_messages(self) -> int:
        messages = await self._repository.get_non_menu_messages()
        if not messages:
            return 0

        deleted_ids: list[int] = []
        batch_size = 100

        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
            batch_message_ids = [m.message_id for m in batch]
            batch_db_ids = [m.id for m in batch]

            try:
                await self._bot.delete_messages(
                    chat_id=self._chat_id,
                    message_ids=batch_message_ids,
                )
                deleted_ids.extend(batch_db_ids)
            except TelegramBadRequest as e:
                logger.warning("Bulk delete failed: %s", e)
                deleted_ids.extend(batch_db_ids)
            except TelegramForbiddenError as e:
                logger.error("No permission to delete messages: %s", e)

        if deleted_ids:
            await self._repository.delete_by_ids(deleted_ids)

        return len(deleted_ids)
