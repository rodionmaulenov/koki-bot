"""Girl's appeal flow: start → video → text → notify manager."""
import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka

from callbacks.appeal import AppealAction, AppealCallback
from config import Settings
from keyboards.appeal import appeal_review_keyboard

from repositories.course_repository import CourseRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.video_service import VideoService
from states.appeal import AppealStates
from templates import AppealTemplates, format_remaining
from utils.telegram_retry import tg_retry
from utils.time import get_tashkent_now

logger = logging.getLogger(__name__)

router = Router()

# Topic icon for appeal in progress
TOPIC_ICON_APPEAL = 5377316857231450742  # ❓

DELETE_DELAY_SECONDS = 3


# ──────────────────────────────────────────────
# Girl starts appeal (callback from "Апелляция" button)
# ──────────────────────────────────────────────


@router.callback_query(AppealCallback.filter(F.action == AppealAction.START))
async def on_start_appeal(
    callback: CallbackQuery,
    callback_data: AppealCallback,
    state: FSMContext,
    course_repository: FromDishka[CourseRepository],
) -> None:
    """Girl pressed 'Апелляция' button."""
    # Atomic: refused → appeal (protects against double-click)
    started = await course_repository.start_appeal(callback_data.course_id)
    if not started:
        await callback.answer()
        return

    # Remove appeal button from the message
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass

    # Start FSM: ask for video (send to girl's private chat, not the callback's chat)
    await state.set_state(AppealStates.video)
    await state.update_data(course_id=callback_data.course_id)
    try:
        await tg_retry(
            callback.bot.send_message,
            chat_id=callback.from_user.id,
            text=AppealTemplates.ask_video(),
        )
    except TelegramForbiddenError:
        logger.info("Girl blocked bot, telegram_id=%d", callback.from_user.id)
        await state.clear()
        await callback.answer()
        return
    await callback.answer()

    logger.info(
        "Appeal started for course_id=%d by user=%d",
        callback_data.course_id, callback.from_user.id,
    )


# ──────────────────────────────────────────────
# Appeal FSM: Step 1 — Video
# ──────────────────────────────────────────────


@router.message(AppealStates.video, F.video_note)
async def on_appeal_video_note(
    message: Message,
    state: FSMContext,
) -> None:
    await _save_appeal_video(message, message.video_note.file_id, state)


@router.message(AppealStates.video, F.video)
async def on_appeal_video(
    message: Message,
    state: FSMContext,
) -> None:
    await _save_appeal_video(message, message.video.file_id, state)


@router.message(AppealStates.video, F.document)
async def on_appeal_video_document(
    message: Message,
    state: FSMContext,
) -> None:
    mime = message.document.mime_type or ""
    if not mime.startswith("video/"):
        await _delete_after_delay(message)
        warn = await message.answer(AppealTemplates.video_only())
        await _delete_after_delay(warn)
        return
    await _save_appeal_video(message, message.document.file_id, state)


@router.message(AppealStates.video)
async def on_appeal_video_invalid(message: Message) -> None:
    """Any non-video content during video step."""
    await _delete_after_delay(message)
    warn = await message.answer(AppealTemplates.video_only())
    await _delete_after_delay(warn)


async def _save_appeal_video(
    message: Message, file_id: str, state: FSMContext,
) -> None:
    """Save video file_id and move to text step."""
    await state.update_data(appeal_video=file_id)
    await state.set_state(AppealStates.text)
    await message.answer(AppealTemplates.ask_text())


# ──────────────────────────────────────────────
# Appeal FSM: Step 2 — Text
# ──────────────────────────────────────────────


@router.message(AppealStates.text, F.text)
async def on_appeal_text(
    message: Message,
    state: FSMContext,
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    manager_repository: FromDishka[ManagerRepository],
    video_service: FromDishka[VideoService],
    settings: FromDishka[Settings],
) -> None:
    """Girl sent appeal text — save to DB, notify topic and manager."""
    data = await state.get_data()
    course_id = data.get("course_id")
    appeal_video = data.get("appeal_video")

    if not course_id or not appeal_video:
        logger.error("Appeal FSM data missing: course_id=%s, video=%s", course_id, appeal_video)
        await message.answer(AppealTemplates.appeal_race_condition())
        await state.clear()
        return

    appeal_text = message.text.strip()
    if not appeal_text:
        warn = await message.answer(AppealTemplates.text_only())
        await _delete_after_delay(warn)
        return

    # Save to DB
    try:
        await course_repository.save_appeal_data(course_id, appeal_video, appeal_text)
    except Exception:
        logger.exception("Failed to save appeal data for course_id=%d", course_id)
        await message.answer(AppealTemplates.appeal_race_condition())
        await state.clear()
        return

    # Clear FSM
    await state.clear()

    # Notify girl
    await message.answer(AppealTemplates.appeal_submitted())

    # Get course, user, manager for topic notifications
    course = await course_repository.get_by_id(course_id)
    if course is None:
        return

    user = await user_repository.get_by_id(course.user_id)
    if user is None:
        return

    topic_id = user.topic_id
    if not topic_id:
        return

    # Reopen topic + change icon → ❓
    try:
        await tg_retry(
            message.bot.reopen_forum_topic,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
        )
    except TelegramBadRequest:
        pass  # Topic might already be open
    except Exception:
        logger.warning("Failed to reopen topic_id=%d", topic_id)

    try:
        await tg_retry(
            message.bot.edit_forum_topic,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
            icon_custom_emoji_id=str(TOPIC_ICON_APPEAL),
        )
    except Exception:
        logger.warning("Failed to change topic icon for topic_id=%d", topic_id)

    # Send video to topic
    try:
        await tg_retry(
            message.bot.send_video,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
            video=appeal_video,
        )
    except Exception:
        logger.exception("Failed to send appeal video to topic_id=%d", topic_id)

    # Send text + review buttons to topic
    try:
        await tg_retry(
            message.bot.send_message,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
            text=AppealTemplates.topic_appeal_submitted(appeal_text),
            reply_markup=appeal_review_keyboard(course_id),
        )
    except Exception:
        logger.exception("Failed to send appeal text to topic_id=%d", topic_id)

    # Notify manager
    manager = await manager_repository.get_by_id(user.manager_id)
    if manager is None:
        return

    deadline = video_service.calculate_deadline(course)
    deadline_str = deadline.strftime("%d.%m %H:%M")

    now = get_tashkent_now()
    delta = deadline - now
    total_minutes = max(int(delta.total_seconds()) // 60, 0)
    hours, minutes = divmod(total_minutes, 60)
    remaining = format_remaining(hours, minutes)

    # DM to manager
    try:
        await tg_retry(
            message.bot.send_message,
            chat_id=manager.telegram_id,
            text=AppealTemplates.manager_appeal_dm(
                user.name, deadline_str, remaining,
                user.topic_id, settings.kok_group_id,
            ),
            parse_mode="HTML",
        )
    except TelegramForbiddenError:
        logger.info(
            "Manager %s (id=%d) hasn't started bot, skipping DM",
            manager.name, manager.telegram_id,
        )
    except Exception:
        logger.warning(
            "Failed to send appeal DM to manager %s (id=%d)",
            manager.name, manager.telegram_id,
        )

    # General topic
    kwargs: dict[str, object] = {
        "chat_id": settings.kok_group_id,
        "text": AppealTemplates.general_appeal_request(
            manager.name, user.name, deadline_str, remaining,
            user.topic_id, settings.kok_group_id,
        ),
        "parse_mode": "HTML",
    }
    if settings.kok_general_topic_id:
        kwargs["message_thread_id"] = settings.kok_general_topic_id
    try:
        await tg_retry(message.bot.send_message, **kwargs)
    except Exception:
        logger.warning("Failed to send appeal request to general topic")

    logger.info(
        "Appeal submitted for course_id=%d, notified manager %s",
        course_id, manager.name,
    )


@router.message(AppealStates.text)
async def on_appeal_text_invalid(message: Message) -> None:
    """Any non-text content during text step."""
    await _delete_after_delay(message)
    warn = await message.answer(AppealTemplates.text_only())
    await _delete_after_delay(warn)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


async def _delete_after_delay(message: Message) -> None:
    """Delete message after a short delay (fire-and-forget)."""
    asyncio.create_task(_delete_message_delayed(message))


async def _delete_message_delayed(message: Message) -> None:
    """Wait then delete — runs as background task."""
    await asyncio.sleep(DELETE_DELAY_SECONDS)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    except Exception:
        logger.debug(
            "Failed to delete message %d in chat %d",
            message.message_id, message.chat.id,
        )
