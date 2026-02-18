import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery
from dishka.integrations.aiogram import FromDishka

from callbacks.card import CardAction, CardCallback
from config import Settings
from keyboards.card import card_keyboard
from models.enums import CourseStatus
from repositories.course_repository import CourseRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from templates import CardTemplates, OnboardingTemplates
from utils.telegram_retry import tg_retry

logger = logging.getLogger(__name__)

router = Router()

EXTENSION_DAYS = 21

# Topic icon for completed course
TOPIC_ICON_COMPLETED = 5368324170671202286  # ✅


# ──────────────────────────────────────────────
# Extend course (+21 days)
# ──────────────────────────────────────────────


@router.callback_query(CardCallback.filter(F.action == CardAction.EXTEND))
async def on_extend(
    callback: CallbackQuery,
    callback_data: CardCallback,
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    manager_repository: FromDishka[ManagerRepository],
    settings: FromDishka[Settings],
) -> None:
    """Manager pressed 'Продлить +21 день' on registration card."""
    course = await course_repository.get_by_id(callback_data.course_id)
    if course is None or course.status != CourseStatus.ACTIVE:
        await callback.answer(CardTemplates.course_not_active(), show_alert=True)
        return

    if course.extended:
        await callback.answer(CardTemplates.already_extended(), show_alert=True)
        return

    old_total = course.total_days
    new_total = old_total + EXTENSION_DAYS

    extended = await course_repository.extend_course(course.id, new_total)
    if not extended:
        await callback.answer(CardTemplates.already_handled(), show_alert=True)
        return

    # Edit card message: remove "Продлить" button, keep "Завершить"
    if callback.message:
        try:
            await callback.message.edit_reply_markup(
                reply_markup=card_keyboard(course.id, can_extend=False),
            )
        except TelegramBadRequest:
            pass

    # Send extension notice to topic
    user = await user_repository.get_by_id(course.user_id)
    if user and user.topic_id:
        try:
            await tg_retry(
                callback.bot.send_message,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                text=CardTemplates.topic_extended(old_total, new_total),
            )
        except Exception:
            logger.warning("Failed to send extend notice to topic_id=%d", user.topic_id)

        # Update topic name with new total
        manager = await manager_repository.get_by_id(user.manager_id)
        manager_name = manager.name if manager else "?"
        name_parts = user.name.split() if user.name else []
        topic_title = OnboardingTemplates.topic_name(
            last_name=name_parts[0] if name_parts else "Unknown",
            first_name=name_parts[1] if len(name_parts) > 1 else "",
            patronymic=" ".join(name_parts[2:]) if len(name_parts) > 2 else None,
            manager_name=manager_name,
            current_day=course.current_day,
            total_days=new_total,
        )
        try:
            await tg_retry(
                callback.bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                name=topic_title,
            )
        except Exception:
            logger.warning("Failed to update topic name for topic_id=%d", user.topic_id)

    # Notify girl in private chat
    if user and user.telegram_id:
        try:
            await tg_retry(
                callback.bot.send_message,
                chat_id=user.telegram_id,
                text=CardTemplates.private_extended(),
            )
        except TelegramForbiddenError:
            logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)
        except Exception:
            logger.warning("Failed to send extend notice to telegram_id=%d", user.telegram_id)

    await callback.answer()
    logger.info(
        "Manager %s extended course_id=%d (%d → %d days)",
        callback.from_user.id, course.id, old_total, new_total,
    )


# ──────────────────────────────────────────────
# Complete course (early termination by manager)
# ──────────────────────────────────────────────


@router.callback_query(CardCallback.filter(F.action == CardAction.COMPLETE))
async def on_complete(
    callback: CallbackQuery,
    callback_data: CardCallback,
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    settings: FromDishka[Settings],
) -> None:
    """Manager pressed 'Завершить программу' on registration card."""
    course = await course_repository.get_by_id(callback_data.course_id)
    if course is None or course.status != CourseStatus.ACTIVE:
        await callback.answer(CardTemplates.course_not_active(), show_alert=True)
        return

    completed = await course_repository.complete_course_active(course.id)
    if not completed:
        await callback.answer(CardTemplates.already_handled(), show_alert=True)
        return

    # Edit card message: remove buttons
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass

    user = await user_repository.get_by_id(course.user_id)

    # Send completion notice to topic
    if user and user.topic_id:
        try:
            await tg_retry(
                callback.bot.send_message,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                text=CardTemplates.topic_completed_early(
                    course.current_day, course.total_days,
                ),
            )
        except Exception:
            logger.warning("Failed to send complete notice to topic_id=%d", user.topic_id)

        # Change topic icon → ✅
        try:
            await tg_retry(
                callback.bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                icon_custom_emoji_id=str(TOPIC_ICON_COMPLETED),
            )
        except Exception:
            logger.warning("Failed to change topic icon for topic_id=%d", user.topic_id)

        # Close topic
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
        try:
            await tg_retry(
                callback.bot.send_message,
                chat_id=user.telegram_id,
                text=CardTemplates.private_completed_early(),
            )
        except TelegramForbiddenError:
            logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)
        except Exception:
            logger.warning("Failed to send complete notice to telegram_id=%d", user.telegram_id)

    await callback.answer()
    logger.info(
        "Manager %s completed course_id=%d early (day %d/%d)",
        callback.from_user.id, course.id, course.current_day, course.total_days,
    )
