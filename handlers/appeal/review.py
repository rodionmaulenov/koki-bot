"""Manager's appeal review: accept / decline."""
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery
from dishka.integrations.aiogram import FromDishka

from callbacks.appeal import AppealAction, AppealCallback
from config import Settings
from filters.roles import RoleFilter
from keyboards.card import card_keyboard
from models.enums import CourseStatus, ManagerRole
from repositories.course_repository import CourseRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from templates import AppealTemplates, fallback_manager_name
from utils.telegram_retry import tg_retry

logger = logging.getLogger(__name__)

router = Router()
router.callback_query.filter(RoleFilter(ManagerRole.MANAGER))

# Topic icon for active course (appeal accepted → back to active)
TOPIC_ICON_ACTIVE = 5310094636159607472  # 💊
# Topic icon for refused course (appeal declined)
TOPIC_ICON_REFUSED = 5379748062124056162  # ❗️


@router.callback_query(AppealCallback.filter(F.action == AppealAction.ACCEPT))
async def on_appeal_accept(
    callback: CallbackQuery,
    callback_data: AppealCallback,
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    settings: FromDishka[Settings],
) -> None:
    """Manager accepted the appeal — reactivate course."""
    course = await course_repository.get_by_id(callback_data.course_id)
    if course is None or course.status != CourseStatus.APPEAL:
        await callback.answer(AppealTemplates.appeal_already_handled(), show_alert=True)
        return

    new_appeal_count = course.appeal_count + 1
    accepted = await course_repository.accept_appeal(course.id, new_appeal_count)
    if not accepted:
        await callback.answer(AppealTemplates.appeal_already_handled(), show_alert=True)
        return

    # Edit topic message: remove buttons, show accepted text
    if callback.message:
        try:
            await callback.message.edit_text(
                AppealTemplates.topic_appeal_accepted(
                    new_appeal_count, AppealTemplates.MAX_APPEALS,
                ),
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass

    # Change topic icon ❓ → 💊
    user = await user_repository.get_by_id(course.user_id)
    if user and user.topic_id:
        try:
            await tg_retry(
                callback.bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                icon_custom_emoji_id=str(TOPIC_ICON_ACTIVE),
            )
        except Exception:
            logger.warning("Failed to change topic icon for topic_id=%d", user.topic_id)

    # Notify girl in private chat
    if user and user.telegram_id:
        try:
            await tg_retry(
                callback.bot.send_message,
                chat_id=user.telegram_id,
                text=AppealTemplates.appeal_accepted(new_appeal_count),
            )
        except TelegramForbiddenError:
            logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)
        except Exception:
            logger.warning("Failed to send appeal accepted to telegram_id=%d", user.telegram_id)

    # Restore card buttons on registration card in topic
    if user and user.topic_id and course.registration_message_id:
        try:
            await tg_retry(
                callback.bot.edit_message_reply_markup,
                chat_id=settings.kok_group_id,
                message_id=course.registration_message_id,
                reply_markup=card_keyboard(course.id, can_extend=not course.extended),
            )
        except TelegramBadRequest:
            logger.debug(
                "Cannot edit registration card message_id=%d",
                course.registration_message_id,
            )
        except Exception:
            logger.warning("Failed to restore card buttons for course_id=%d", course.id)

    await callback.answer()
    logger.info(
        "Manager %s accepted appeal for course_id=%d (appeal_count=%d)",
        callback.from_user.id, course.id, new_appeal_count,
    )


@router.callback_query(AppealCallback.filter(F.action == AppealAction.DECLINE))
async def on_appeal_decline(
    callback: CallbackQuery,
    callback_data: AppealCallback,
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    manager_repository: FromDishka[ManagerRepository],
    settings: FromDishka[Settings],
) -> None:
    """Manager declined the appeal — refuse course permanently."""
    course = await course_repository.get_by_id(callback_data.course_id)
    if course is None or course.status != CourseStatus.APPEAL:
        await callback.answer(AppealTemplates.appeal_already_handled(), show_alert=True)
        return

    new_appeal_count = course.appeal_count + 1
    declined = await course_repository.decline_appeal(course.id, new_appeal_count)
    if not declined:
        await callback.answer(AppealTemplates.appeal_already_handled(), show_alert=True)
        return

    # Edit topic message: remove buttons, show declined text
    if callback.message:
        try:
            await callback.message.edit_text(
                AppealTemplates.topic_appeal_declined(
                    new_appeal_count, AppealTemplates.MAX_APPEALS,
                ),
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass

    # Change topic icon ❓ → ❗️ + close topic
    user = await user_repository.get_by_id(course.user_id)
    if user and user.topic_id:
        try:
            await tg_retry(
                callback.bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                icon_custom_emoji_id=str(TOPIC_ICON_REFUSED),
            )
        except Exception:
            logger.warning("Failed to change topic icon for topic_id=%d", user.topic_id)
        try:
            await tg_retry(
                callback.bot.close_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
            )
        except Exception:
            logger.warning("Failed to close topic_id=%d", user.topic_id)

    # Notify girl in private chat
    if user and user.telegram_id:
        manager = await manager_repository.get_by_id(user.manager_id)
        manager_name = manager.name if manager else fallback_manager_name()
        try:
            await tg_retry(
                callback.bot.send_message,
                chat_id=user.telegram_id,
                text=AppealTemplates.appeal_declined(manager_name),
            )
        except TelegramForbiddenError:
            logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)
        except Exception:
            logger.warning("Failed to send appeal declined to telegram_id=%d", user.telegram_id)

    await callback.answer()
    logger.info(
        "Manager %s declined appeal for course_id=%d (appeal_count=%d)",
        callback.from_user.id, course.id, new_appeal_count,
    )
