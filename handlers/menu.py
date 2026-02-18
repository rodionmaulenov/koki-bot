import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka
from redis.asyncio import Redis

from callbacks.menu import MenuAction, MenuCallback
from keyboards.menu import main_menu_keyboard
from repositories.commands_messages_repository import CommandsMessagesRepository
from templates import MenuTemplates
from topic_access.message_middleware import ADD_ACTIVE_KEY_PREFIX
from topic_access.service import CommandsMessagesService
from topic_access.tracked_bot import TrackedBot

logger = logging.getLogger(__name__)

router = Router()

SERVICE_FILTER = (
    F.forum_topic_edited
    | F.forum_topic_created
    | F.forum_topic_closed
    | F.forum_topic_reopened
)


async def ensure_menu(
    bot: TrackedBot,
    chat_id: int,
    thread_id: int,
    repository: CommandsMessagesRepository,
) -> None:
    menu_text = MenuTemplates.main_menu()
    keyboard = main_menu_keyboard()

    try:
        existing = await repository.get_menu_message()
    except Exception:
        logger.exception("Failed to get menu message from DB")
        existing = None

    if existing:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=existing.message_id,
                text=menu_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            logger.info("Menu updated (message_id=%d)", existing.message_id)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                logger.info(
                    "Menu already up-to-date (message_id=%d)",
                    existing.message_id,
                )
                return
            logger.warning("Cannot edit menu: %s. Sending new.", e)
            try:
                await repository.delete_menu_message()
            except Exception:
                logger.exception("Failed to delete menu message from DB")

    await bot.send_menu_message(
        chat_id=chat_id,
        message_thread_id=thread_id,
        text=menu_text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    logger.info("New menu sent")


@router.callback_query(MenuCallback.filter(F.action == MenuAction.CLEAR))
async def on_clear(
    callback: CallbackQuery,
    state: FSMContext,
    commands_messages_service: FromDishka[CommandsMessagesService],
    redis: FromDishka[Redis],
) -> None:
    await state.clear()
    thread_id = callback.message.message_thread_id
    if thread_id:
        try:
            await redis.delete(f"{ADD_ACTIVE_KEY_PREFIX}:{thread_id}")
        except Exception:
            pass
    await commands_messages_service.clear_messages()
    await callback.answer(MenuTemplates.topic_cleared(), show_alert=True)


@router.message(SERVICE_FILTER)
async def delete_service_messages(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest as e:
        logger.warning("Cannot delete service message: %s", e)
