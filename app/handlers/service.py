"""Удаление служебных сообщений Telegram."""

import logging
from aiogram import Router, F
from aiogram.types import Message

from app.config import get_settings

logger = logging.getLogger(__name__)
router = Router()
settings = get_settings()

SERVICE_FILTER = (
    F.forum_topic_edited |
    F.forum_topic_created |
    F.forum_topic_closed |
    F.forum_topic_reopened
)


@router.message(
    SERVICE_FILTER,
    F.chat.id == settings.kok_group_id,  # только в группе КОК
)
async def delete_service_messages(message: Message):
    """Удаляет служебные сообщения о топиках."""
    try:
        await message.delete()
        logger.debug(f"🗑️ Deleted service message {message.message_id}")
    except Exception as e:
        logger.warning(f"⚠️ Could not delete service message: {e}")