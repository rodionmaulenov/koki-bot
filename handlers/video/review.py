import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from dishka.integrations.aiogram import FromDishka

from callbacks.video import VideoAction, VideoCallback
from config import Settings
from utils.time import get_tashkent_now
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.video_service import LATE_THRESHOLD_MINUTES, VideoService
from templates import OnboardingTemplates, VideoTemplates, fallback_manager_name, format_remaining
from utils.telegram_retry import tg_retry

logger = logging.getLogger(__name__)

router = Router()

# Topic icon for refused course
TOPIC_ICON_REFUSED = 5379748062124056162  # ❗️
# Topic icon for active course (first day confirmed by manager)
TOPIC_ICON_ACTIVE = 5310094636159607472  # 💊
# Topic icon for completed course
TOPIC_ICON_COMPLETED = 5368324170671202286  # ✅
# Topic icon for reshoot waiting
TOPIC_ICON_RESHOOT = 5312536423851630001  # 💡


@router.callback_query(VideoCallback.filter(F.action == VideoAction.CONFIRM))
async def on_confirm(
    callback: CallbackQuery,
    callback_data: VideoCallback,
    intake_log_repository: FromDishka[IntakeLogRepository],
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    manager_repository: FromDishka[ManagerRepository],
    video_service: FromDishka[VideoService],
    settings: FromDishka[Settings],
) -> None:
    """Manager confirmed the video — mark day as taken."""
    intake_log = await intake_log_repository.get_by_id(callback_data.log_id)
    if intake_log is None or intake_log.status != "pending_review":
        await callback.answer(VideoTemplates.review_already_handled(), show_alert=True)
        return

    course = await course_repository.get_by_id(intake_log.course_id)
    if course is None:
        logger.error("Course not found for log_id=%d", intake_log.id)
        await callback.answer("Ошибка: курс не найден", show_alert=True)
        return

    # 1. Update DB: intake_log → taken, course.current_day += 1
    confirmed = await video_service.confirm_intake(intake_log.id, course.id, intake_log.day)
    if not confirmed:
        await callback.answer(VideoTemplates.review_already_handled(), show_alert=True)
        return

    # 1.5 Late check (manager confirmed a late video)
    is_late = (
        intake_log.delay_minutes is not None
        and intake_log.delay_minutes > LATE_THRESHOLD_MINUTES
    )
    late_count = 0
    max_strikes = video_service.get_max_strikes(course)

    if is_late:
        try:
            late_count, _ = await video_service.record_late(course)
        except Exception:
            logger.exception("Failed to record late for course_id=%d", course.id)
            is_late = False  # Strike not recorded → don't show late warning

    # 1.6 Completion check (confirmed + last day)
    is_completed = intake_log.day >= course.total_days
    if is_completed:
        try:
            is_completed = await video_service.complete_course(course.id)
        except Exception:
            logger.exception("Failed to complete course_id=%d", course.id)
            is_completed = False

    # 2. Edit topic message: remove buttons, show confirmed/completion text
    if is_completed:
        await _edit_callback_message(
            callback,
            VideoTemplates.topic_completed(intake_log.day, course.total_days),
        )
    else:
        await _edit_callback_message(
            callback,
            VideoTemplates.topic_confirmed(intake_log.day, course.total_days),
        )

    # 3. Edit girl's private message
    user = await user_repository.get_by_id(course.user_id)
    if user and user.telegram_id and intake_log.private_message_id:
        if is_completed:
            await _edit_private_message(
                callback.bot,
                user.telegram_id,
                intake_log.private_message_id,
                VideoTemplates.private_completed(course.total_days),
            )
        elif is_late:
            await _edit_private_message(
                callback.bot,
                user.telegram_id,
                intake_log.private_message_id,
                VideoTemplates.approved_late(
                    intake_log.day, course.total_days, late_count, max_strikes,
                ),
            )
        else:
            await _edit_private_message(
                callback.bot,
                user.telegram_id,
                intake_log.private_message_id,
                VideoTemplates.private_confirmed(intake_log.day, course.total_days),
            )

    # 4. Topic icon + late warning / completion / first day
    if is_completed and user and user.topic_id:
        # Change icon → ✅ + close topic
        try:
            await tg_retry(
                callback.bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                icon_custom_emoji_id=str(TOPIC_ICON_COMPLETED),
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
    elif is_late and user and user.topic_id:
        # Send late warning under the confirmed message
        try:
            await tg_retry(
                callback.bot.send_message,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                text=VideoTemplates.topic_late_warning(late_count, max_strikes),
            )
        except Exception:
            logger.warning("Failed to send late warning to topic_id=%d", user.topic_id)
    elif intake_log.day == 1 and user and user.topic_id:
        # Change topic icon on first day: ⭐ → 💊
        try:
            await tg_retry(
                callback.bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                icon_custom_emoji_id=str(TOPIC_ICON_ACTIVE),
            )
        except Exception:
            logger.warning("Failed to change topic icon for topic_id=%d", user.topic_id)

    # 5. Update topic name with current progress
    if user and user.topic_id:
        try:
            manager = await manager_repository.get_by_id(user.manager_id)
            mgr_name = manager.name if manager else "?"
            name_parts = user.name.split() if user.name else []
            topic_title = OnboardingTemplates.topic_name(
                last_name=name_parts[0] if name_parts else "Unknown",
                first_name=name_parts[1] if len(name_parts) > 1 else "",
                patronymic=" ".join(name_parts[2:]) if len(name_parts) > 2 else None,
                manager_name=mgr_name,
                current_day=intake_log.day,
                total_days=course.total_days,
            )
            await tg_retry(
                callback.bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                name=topic_title,
            )
        except Exception:
            logger.warning("Failed to update topic name for topic_id=%d", user.topic_id)

    await callback.answer()
    logger.info(
        "Manager %s confirmed day %d for course_id=%d%s",
        callback.from_user.id, intake_log.day, course.id,
        " (COMPLETED)" if is_completed else (" (late)" if is_late else ""),
    )


@router.callback_query(VideoCallback.filter(F.action == VideoAction.REJECT))
async def on_reject(
    callback: CallbackQuery,
    callback_data: VideoCallback,
    intake_log_repository: FromDishka[IntakeLogRepository],
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    manager_repository: FromDishka[ManagerRepository],
    video_service: FromDishka[VideoService],
    settings: FromDishka[Settings],
) -> None:
    """Manager rejected the video — refuse the course."""
    intake_log = await intake_log_repository.get_by_id(callback_data.log_id)
    if intake_log is None or intake_log.status != "pending_review":
        await callback.answer(VideoTemplates.review_already_handled(), show_alert=True)
        return

    course = await course_repository.get_by_id(intake_log.course_id)
    if course is None:
        logger.error("Course not found for log_id=%d", intake_log.id)
        await callback.answer("Ошибка: курс не найден", show_alert=True)
        return

    # 1. Update DB: intake_log → rejected, course → refused
    rejected = await video_service.reject_intake(intake_log.id, course.id)
    if not rejected:
        await callback.answer(VideoTemplates.review_already_handled(), show_alert=True)
        return

    # 2. Edit topic message: remove buttons, show rejected text
    await _edit_callback_message(
        callback, VideoTemplates.topic_rejected(),
    )

    # 3. Change topic icon → ❗️
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

    # 4. Edit girl's private message with manager contact (no appeal — manager decision)
    if user and user.telegram_id and intake_log.private_message_id:
        manager = await manager_repository.get_by_id(user.manager_id)
        manager_name = manager.name if manager else fallback_manager_name()
        await _edit_private_message(
            callback.bot,
            user.telegram_id,
            intake_log.private_message_id,
            VideoTemplates.private_rejected(manager_name),
        )

    await callback.answer()
    logger.info(
        "Manager %s rejected day %d for course_id=%d",
        callback.from_user.id, intake_log.day, course.id,
    )


@router.callback_query(VideoCallback.filter(F.action == VideoAction.RESHOOT))
async def on_reshoot(
    callback: CallbackQuery,
    callback_data: VideoCallback,
    intake_log_repository: FromDishka[IntakeLogRepository],
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    video_service: FromDishka[VideoService],
    settings: FromDishka[Settings],
) -> None:
    """Manager requested reshoot — set deadline, notify girl."""
    intake_log = await intake_log_repository.get_by_id(callback_data.log_id)
    if intake_log is None or intake_log.status != "pending_review":
        await callback.answer(VideoTemplates.review_already_handled(), show_alert=True)
        return

    course = await course_repository.get_by_id(intake_log.course_id)
    if course is None:
        logger.error("Course not found for log_id=%d", intake_log.id)
        await callback.answer("Ошибка: курс не найден", show_alert=True)
        return

    # 1. Update DB: status → reshoot, set deadline
    deadline = await video_service.request_reshoot(intake_log.id, course)
    deadline_str = deadline.strftime("%d.%m %H:%M")

    now = get_tashkent_now()
    delta = deadline - now
    total_minutes = max(int(delta.total_seconds()) // 60, 0)
    hours, minutes = divmod(total_minutes, 60)
    remaining_ru = format_remaining(hours, minutes, lang="ru")
    remaining = format_remaining(hours, minutes)

    # 2. Edit topic message: remove buttons, show reshoot text (Russian for manager)
    await _edit_callback_message(
        callback,
        VideoTemplates.topic_reshoot(intake_log.day, deadline_str, remaining_ru),
    )

    # 3. Send reshoot message to girl (uses BOT_LANG)
    user = await user_repository.get_by_id(course.user_id)
    if user and user.telegram_id:
        try:
            await tg_retry(
                callback.bot.send_message,
                chat_id=user.telegram_id,
                text=VideoTemplates.private_reshoot(deadline_str, remaining),
            )
        except TelegramForbiddenError:
            logger.info("Girl blocked bot, telegram_id=%d", user.telegram_id)

    # 4. Change topic icon → 💡 (reshoot waiting)
    if user and user.topic_id:
        try:
            await tg_retry(
                callback.bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=user.topic_id,
                icon_custom_emoji_id=str(TOPIC_ICON_RESHOOT),
            )
        except Exception:
            logger.warning("Failed to change topic icon for topic_id=%d", user.topic_id)

    await callback.answer()
    logger.info(
        "Manager %s requested reshoot for day %d, course_id=%d, deadline=%s",
        callback.from_user.id, intake_log.day, course.id, deadline_str,
    )


async def _edit_callback_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit the message that triggered the callback."""
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass


async def _edit_private_message(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit a message in girl's private chat."""
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest:
        logger.debug(
            "Cannot edit private message chat_id=%d message_id=%d",
            chat_id, message_id,
        )
