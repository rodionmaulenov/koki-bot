from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

if TYPE_CHECKING:
    from topic_access.tracked_bot import TrackedBot

logger = logging.getLogger(__name__)


async def delete_user_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    bot: TrackedBot = message.bot  # type: ignore[assignment]
    if hasattr(bot, "untrack_message"):
        await bot.untrack_message(message.message_id)


async def edit_or_send(
    message: Message,
    state: FSMContext,
    bot_message_id: int | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if bot_message_id is not None:
        try:
            await message.bot.edit_message_text(
                text=text,
                chat_id=message.chat.id,
                message_id=bot_message_id,
                reply_markup=reply_markup,
            )
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                return
            logger.warning("Cannot edit message: %s", e)

    sent = await message.answer(text=text, reply_markup=reply_markup)
    await state.update_data(bot_message_id=sent.message_id)


async def extract_image_file_id(
    message: Message, state: FSMContext, error_text: str,
) -> str | None:
    mime = message.document.mime_type or ""
    if not mime.startswith("image/"):
        data = await state.get_data()
        await delete_user_message(message)
        await edit_or_send(
            message, state, data.get("bot_message_id"),
            text=error_text,
        )
        return None
    return message.document.file_id


async def edit_or_send_callback(
    callback: CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        logger.warning("Cannot edit message: %s", e)
        sent = await callback.message.answer(text=text, reply_markup=reply_markup)
        await state.update_data(bot_message_id=sent.message_id)
