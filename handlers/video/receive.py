import io
import json
import logging
from enum import StrEnum

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup, Message
from dishka.integrations.aiogram import FromDishka
from google.genai import errors as genai_errors

from config import Settings
from keyboards.video import reshoot_review_keyboard, review_keyboard
from models.course import Course
from models.enums import CourseStatus
from models.intake_log import IntakeLog
from models.user import User
from repositories.course_repository import CourseRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.gemini_service import GeminiService
from services.video_service import (
    AI_CONFIDENCE_THRESHOLD,
    LATE_THRESHOLD_MINUTES,
    VideoService,
    WindowStatus,
)
from templates import OnboardingTemplates, VideoTemplates, format_remaining
from utils.telegram_retry import tg_retry
from utils.time import get_tashkent_now

logger = logging.getLogger(__name__)

router = Router()

# Only handle private messages
PRIVATE_FILTER = F.chat.type == "private"

# Topic icon for active course (girl started taking pills)
TOPIC_ICON_ACTIVE = 5310094636159607472  # 💊
# Topic icon for completed course
TOPIC_ICON_COMPLETED = 5368324170671202286  # ✅
# Topic icon for reshoot waiting
TOPIC_ICON_RESHOOT = 5312536423851630001  # 💡


class VideoType(StrEnum):
    VIDEO_NOTE = "video_note"
    VIDEO = "video"


# ──────────────────────────────────────────────
# Video handlers
# ──────────────────────────────────────────────


@router.message(PRIVATE_FILTER, F.video_note)
async def on_video_note(
    message: Message,
    user_repository: FromDishka[UserRepository],
    course_repository: FromDishka[CourseRepository],
    manager_repository: FromDishka[ManagerRepository],
    video_service: FromDishka[VideoService],
    gemini_service: FromDishka[GeminiService],
    settings: FromDishka[Settings],
) -> None:
    await _handle_video(
        message, message.video_note.file_id, "video/mp4", VideoType.VIDEO_NOTE,
        user_repository, course_repository, manager_repository,
        video_service, gemini_service, settings,
    )


@router.message(PRIVATE_FILTER, F.video)
async def on_video(
    message: Message,
    user_repository: FromDishka[UserRepository],
    course_repository: FromDishka[CourseRepository],
    manager_repository: FromDishka[ManagerRepository],
    video_service: FromDishka[VideoService],
    gemini_service: FromDishka[GeminiService],
    settings: FromDishka[Settings],
) -> None:
    mime = message.video.mime_type or "video/mp4"
    await _handle_video(
        message, message.video.file_id, mime, VideoType.VIDEO,
        user_repository, course_repository, manager_repository,
        video_service, gemini_service, settings,
    )


@router.message(PRIVATE_FILTER, F.document)
async def on_video_document(
    message: Message,
    user_repository: FromDishka[UserRepository],
    course_repository: FromDishka[CourseRepository],
    manager_repository: FromDishka[ManagerRepository],
    video_service: FromDishka[VideoService],
    gemini_service: FromDishka[GeminiService],
    settings: FromDishka[Settings],
) -> None:
    mime = message.document.mime_type or ""
    if not mime.startswith("video/"):
        await message.answer(VideoTemplates.video_only())
        return
    await _handle_video(
        message, message.document.file_id, mime, VideoType.VIDEO,
        user_repository, course_repository, manager_repository,
        video_service, gemini_service, settings,
    )


# ──────────────────────────────────────────────
# Catch-all for non-video content in private chat
# ──────────────────────────────────────────────


@router.message(PRIVATE_FILTER)
async def on_private_other(
    message: Message,
    user_repository: FromDishka[UserRepository],
    course_repository: FromDishka[CourseRepository],
    video_service: FromDishka[VideoService],
) -> None:
    user, course = await _get_user_and_active_course(
        message, user_repository, course_repository,
    )
    if course is None:
        await message.answer(VideoTemplates.video_only())
        return

    if course.current_day >= course.total_days:
        await message.answer(VideoTemplates.course_completed(course.total_days))
        return

    # === RESHOOT PLUGIN ===
    reshoot_log = await video_service.get_pending_reshoot(course.id)
    if reshoot_log:
        now = get_tashkent_now()
        if reshoot_log.reshoot_deadline and now > reshoot_log.reshoot_deadline:
            await video_service.expire_reshoot(reshoot_log.id, course.id)
            await message.answer(VideoTemplates.reshoot_expired())
        else:
            deadline_str = reshoot_log.reshoot_deadline.strftime("%d.%m %H:%M") if reshoot_log.reshoot_deadline else ""
            if reshoot_log.reshoot_deadline:
                delta = reshoot_log.reshoot_deadline - now
                total_min = max(int(delta.total_seconds()) // 60, 0)
                h, m = divmod(total_min, 60)
                remaining = format_remaining(h, m)
            else:
                remaining = ""
            await message.answer(VideoTemplates.private_reshoot(deadline_str, remaining))
        return
    # === END RESHOOT ===

    window_status, open_time = video_service.check_window(course)

    if window_status == WindowStatus.EARLY:
        await message.answer(VideoTemplates.window_early(open_time))
        return

    if window_status == WindowStatus.OPEN:
        existing = await video_service.get_today_log(course)
        if existing:
            await message.answer(VideoTemplates.already_sent_today())
        else:
            await message.answer(VideoTemplates.send_video())
        return

    await message.answer(VideoTemplates.video_only())


# ──────────────────────────────────────────────
# Core logic
# ──────────────────────────────────────────────


async def _get_user_and_active_course(
    message: Message,
    user_repository: UserRepository,
    course_repository: CourseRepository,
) -> tuple[User | None, Course | None]:
    """Get user and their active course. Returns (None, None) if not found."""
    if not message.from_user:
        return None, None

    user = await user_repository.get_by_telegram_id(message.from_user.id)
    if user is None:
        return None, None

    course = await course_repository.get_active_by_user_id(user.id)
    if course is None or course.status != CourseStatus.ACTIVE:
        return user, None

    return user, course


async def _handle_video(
    message: Message,
    file_id: str,
    mime_type: str,
    video_type: VideoType,
    user_repository: UserRepository,
    course_repository: CourseRepository,
    manager_repository: ManagerRepository,
    video_service: VideoService,
    gemini_service: GeminiService,
    settings: Settings,
) -> None:
    """Process video from girl: validate → AI check → record → notify."""
    # 1. Get active course
    user, course = await _get_user_and_active_course(
        message, user_repository, course_repository,
    )
    if course is None:
        await message.answer(VideoTemplates.no_active_course())
        return

    # 2. Check if course is completed
    if course.current_day >= course.total_days:
        await message.answer(VideoTemplates.course_completed(course.total_days))
        return

    # === RESHOOT PLUGIN ===
    reshoot_log = await video_service.get_pending_reshoot(course.id)
    if reshoot_log:
        await _handle_reshoot(
            message, file_id, mime_type, video_type,
            user, course, reshoot_log,
            manager_repository, video_service, gemini_service, settings,
        )
        return
    # === END RESHOOT ===

    # 3. Check intake window
    window_status, open_time = video_service.check_window(course)
    if window_status == WindowStatus.EARLY:
        await message.answer(VideoTemplates.window_early(open_time))
        return
    if window_status == WindowStatus.CLOSED:
        await message.answer(VideoTemplates.window_closed())
        return

    # 4. Check if already sent today
    existing_log = await video_service.get_today_log(course)
    if existing_log:
        await message.answer(VideoTemplates.already_sent_today())
        return

    # 5. Show processing message
    processing_msg = await message.answer(VideoTemplates.processing())

    # 6. Download video and run AI check
    try:
        buffer = io.BytesIO()
        await message.bot.download(file_id, destination=buffer)
        video_bytes = buffer.getvalue()
    except Exception:
        logger.exception("Failed to download video file_id=%s", file_id)
        await _edit_safe(processing_msg, VideoTemplates.ai_error())
        return

    try:
        result = await gemini_service.process_video(video_bytes, mime_type)
    except (genai_errors.APIError, ValueError, json.JSONDecodeError):
        logger.exception("Gemini video analysis failed, file_id=%s", file_id)
        await _edit_safe(processing_msg, VideoTemplates.ai_error())
        return

    approved = result.approved and result.confidence >= AI_CONFIDENCE_THRESHOLD
    next_day = course.current_day + 1

    # 7. Record intake
    try:
        intake_log = await video_service.record_intake(
            course=course,
            video_file_id=file_id,
            approved=approved,
            confidence=result.confidence,
        )
    except Exception:
        logger.exception(
            "Failed to record intake for course_id=%d day=%d",
            course.id, next_day,
        )
        await _edit_safe(processing_msg, VideoTemplates.ai_error())
        return

    # 7.5 Late check (only for approved videos)
    is_late = (
        approved
        and intake_log.delay_minutes is not None
        and intake_log.delay_minutes > LATE_THRESHOLD_MINUTES
    )
    late_count = 0
    max_strikes = video_service.get_max_strikes(course)

    if is_late:
        try:
            late_count, _ = await video_service.record_late(course)
        except Exception:
            logger.warning("record_late failed, retrying course_id=%d", course.id)
            try:
                late_count, _ = await video_service.record_late(course)
            except Exception:
                logger.exception("record_late retry failed for course_id=%d", course.id)
                is_late = False

    # 7.6 Completion check (approved + last day)
    is_completed = approved and next_day >= course.total_days
    if is_completed:
        try:
            is_completed = await video_service.complete_course(course.id)
        except Exception:
            logger.exception("Failed to complete course_id=%d", course.id)
            is_completed = False

    # 8. Notify girl
    if is_completed:
        await _edit_safe(
            processing_msg,
            VideoTemplates.private_completed(course.total_days),
        )
    elif is_late:
        await _edit_safe(
            processing_msg,
            VideoTemplates.approved_late(next_day, course.total_days, late_count, max_strikes),
        )
    elif approved:
        await _edit_safe(
            processing_msg,
            VideoTemplates.approved(next_day, course.total_days),
        )
    else:
        await _edit_safe(processing_msg, VideoTemplates.pending_review())

    # 9. Save private message ID for later editing (manager confirm/reject/reshoot)
    if not is_completed:
        try:
            await video_service.save_private_message_id(
                intake_log.id, processing_msg.message_id,
            )
        except Exception:
            logger.warning(
                "Failed to save private_message_id for log_id=%d", intake_log.id,
            )

    # 10. Send to topic (user already fetched above — no double query)
    topic_id = user.topic_id if user else None

    if is_completed and topic_id:
        await _send_completion_to_topic(
            message.bot, settings, topic_id, file_id, video_type,
            next_day, course.total_days,
        )
    elif topic_id:
        await _send_to_topic(
            message.bot, settings, topic_id, file_id, video_type,
            approved, next_day, course, result.reason, intake_log.id,
        )
        if is_late:
            await _send_late_warning_to_topic(
                message.bot, settings, topic_id, late_count, max_strikes,
            )

    # 10.5 Update topic name with current progress
    if approved and topic_id and user:
        await _update_topic_name(
            message.bot, settings, topic_id, user, manager_repository,
            next_day, course.total_days,
        )

    # 11. Notify manager if pending review
    if not approved and not is_completed and user:
        await _notify_manager(
            message.bot, settings, user, course,
            video_service, manager_repository,
        )


async def _handle_reshoot(
    message: Message,
    file_id: str,
    mime_type: str,
    video_type: VideoType,
    user: User | None,
    course: Course,
    reshoot_log: IntakeLog,
    manager_repository: ManagerRepository,
    video_service: VideoService,
    gemini_service: GeminiService,
    settings: Settings,
) -> None:
    """Handle reshoot video: check deadline → AI → update existing log."""
    # 1. Check deadline — if expired, refuse course immediately
    now = get_tashkent_now()
    if reshoot_log.reshoot_deadline and now > reshoot_log.reshoot_deadline:
        await video_service.expire_reshoot(reshoot_log.id, course.id)
        await message.answer(VideoTemplates.reshoot_expired())
        return

    # 2. Show processing message
    processing_msg = await message.answer(VideoTemplates.processing())

    # 3. Download video and run AI check
    try:
        buffer = io.BytesIO()
        await message.bot.download(file_id, destination=buffer)
        video_bytes = buffer.getvalue()
    except Exception:
        logger.exception("Failed to download reshoot video file_id=%s", file_id)
        await _edit_safe(processing_msg, VideoTemplates.ai_error())
        return

    try:
        result = await gemini_service.process_video(video_bytes, mime_type)
    except (genai_errors.APIError, ValueError, json.JSONDecodeError):
        logger.exception("Gemini reshoot analysis failed, file_id=%s", file_id)
        await _edit_safe(processing_msg, VideoTemplates.ai_error())
        return

    approved = result.approved and result.confidence >= AI_CONFIDENCE_THRESHOLD

    # 4. Update existing intake_log (no new record)
    try:
        if approved:
            await video_service.accept_reshoot(
                log_id=reshoot_log.id,
                course_id=course.id,
                day=reshoot_log.day,
                video_file_id=file_id,
                confidence=result.confidence,
                verified_by="gemini",
            )
        else:
            await video_service.reshoot_pending_review(
                log_id=reshoot_log.id,
                video_file_id=file_id,
                confidence=result.confidence,
            )
    except Exception:
        logger.exception(
            "Failed to update reshoot for log_id=%d", reshoot_log.id,
        )
        await _edit_safe(processing_msg, VideoTemplates.ai_error())
        return

    # 4.5 Completion check
    is_completed = approved and reshoot_log.day >= course.total_days
    if is_completed:
        try:
            is_completed = await video_service.complete_course(course.id)
        except Exception:
            logger.exception("Failed to complete course_id=%d", course.id)
            is_completed = False

    # 5. Notify girl
    if is_completed:
        await _edit_safe(
            processing_msg,
            VideoTemplates.private_completed(course.total_days),
        )
    elif approved:
        await _edit_safe(
            processing_msg,
            VideoTemplates.approved(reshoot_log.day, course.total_days),
        )
    else:
        await _edit_safe(processing_msg, VideoTemplates.pending_review())

    # 6. Save private message ID for later editing
    if not is_completed:
        try:
            await video_service.save_private_message_id(
                reshoot_log.id, processing_msg.message_id,
            )
        except Exception:
            logger.warning(
                "Failed to save private_message_id for reshoot log_id=%d",
                reshoot_log.id,
            )

    # 7. Send to topic
    topic_id = user.topic_id if user else None
    if is_completed and topic_id:
        await _send_completion_to_topic(
            message.bot, settings, topic_id, file_id, video_type,
            reshoot_log.day, course.total_days,
        )
    elif topic_id:
        await _send_to_topic(
            message.bot, settings, topic_id, file_id, video_type,
            approved, reshoot_log.day, course, result.reason, reshoot_log.id,
            is_reshoot=True,
        )

    # 7.5 Update topic name with current progress
    if approved and topic_id and user:
        await _update_topic_name(
            message.bot, settings, topic_id, user, manager_repository,
            reshoot_log.day, course.total_days,
        )

    # 8. Notify manager if pending review
    if not approved and not is_completed and user:
        await _notify_manager(
            message.bot, settings, user, course,
            video_service, manager_repository,
        )


async def _send_to_topic(
    bot: Bot,
    settings: Settings,
    topic_id: int,
    file_id: str,
    video_type: VideoType,
    approved: bool,
    day: int,
    course: Course,
    reason: str,
    log_id: int,
    *,
    is_reshoot: bool = False,
) -> None:
    """Forward video and status to the girl's topic in KOK group."""
    # 1. Send video (always without text)
    try:
        if video_type == VideoType.VIDEO_NOTE:
            await tg_retry(
                bot.send_video_note,
                chat_id=settings.kok_group_id,
                message_thread_id=topic_id,
                video_note=file_id,
            )
        else:
            await tg_retry(
                bot.send_video,
                chat_id=settings.kok_group_id,
                message_thread_id=topic_id,
                video=file_id,
            )
    except Exception:
        logger.exception("Failed to send video to topic_id=%d", topic_id)
        return

    # 2. Send status message (with buttons if pending review)
    if approved:
        text = VideoTemplates.topic_approved(day, course.total_days)
        markup = None
    else:
        text = VideoTemplates.topic_pending_review(day, course.total_days, reason)
        markup = reshoot_review_keyboard(log_id) if is_reshoot else review_keyboard(log_id)

    try:
        await tg_retry(
            bot.send_message,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
            text=text,
            reply_markup=markup,
        )
    except Exception:
        logger.exception("Failed to send status message for log_id=%d", log_id)

    # Change topic icon
    if is_reshoot and approved:
        # Reshoot approved → change 💡 back to 💊
        try:
            await tg_retry(
                bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=topic_id,
                icon_custom_emoji_id=str(TOPIC_ICON_ACTIVE),
            )
        except Exception:
            logger.warning("Failed to change topic icon for topic_id=%d", topic_id)
    elif day == 1:
        # First day: ⭐ → 💊
        try:
            await tg_retry(
                bot.edit_forum_topic,
                chat_id=settings.kok_group_id,
                message_thread_id=topic_id,
                icon_custom_emoji_id=str(TOPIC_ICON_ACTIVE),
            )
        except Exception:
            logger.warning("Failed to change topic icon for topic_id=%d", topic_id)


async def _notify_manager(
    bot: Bot,
    settings: Settings,
    user: User,
    course: Course,
    video_service: VideoService,
    manager_repository: ManagerRepository,
) -> None:
    """Send review notifications to manager (DM + general topic)."""
    manager = await manager_repository.get_by_id(user.manager_id)
    if manager is None:
        logger.warning("Manager not found for manager_id=%d", user.manager_id)
        return

    deadline = video_service.calculate_deadline(course)
    deadline_str = deadline.strftime("%d.%m %H:%M")

    # Calculate remaining time
    now = get_tashkent_now()
    delta = deadline - now
    total_minutes = max(int(delta.total_seconds()) // 60, 0)
    hours, minutes = divmod(total_minutes, 60)
    remaining = format_remaining(hours, minutes, lang="ru")

    # 1. DM to manager (may fail if manager hasn't started bot)
    try:
        await tg_retry(
            bot.send_message,
            chat_id=manager.telegram_id,
            text=VideoTemplates.manager_review_dm(
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
            "Failed to send DM to manager %s (id=%d)",
            manager.name, manager.telegram_id,
        )

    # 2. General topic
    kwargs: dict[str, object] = {
        "chat_id": settings.kok_group_id,
        "text": VideoTemplates.general_review_request(
            manager.name, user.name, deadline_str, remaining,
            user.topic_id, settings.kok_group_id,
        ),
        "parse_mode": "HTML",
    }
    if settings.kok_general_topic_id:
        kwargs["message_thread_id"] = settings.kok_general_topic_id
    try:
        await tg_retry(bot.send_message, **kwargs)
    except Exception:
        logger.warning("Failed to send to general topic for manager %s", manager.name)


async def _send_completion_to_topic(
    bot: Bot,
    settings: Settings,
    topic_id: int,
    file_id: str,
    video_type: VideoType,
    day: int,
    total_days: int,
) -> None:
    """Send video + completion message, change icon → ✅, close topic."""
    # 1. Send video
    try:
        if video_type == VideoType.VIDEO_NOTE:
            await tg_retry(
                bot.send_video_note,
                chat_id=settings.kok_group_id,
                message_thread_id=topic_id,
                video_note=file_id,
            )
        else:
            await tg_retry(
                bot.send_video,
                chat_id=settings.kok_group_id,
                message_thread_id=topic_id,
                video=file_id,
            )
    except Exception:
        logger.exception("Failed to send video to topic_id=%d", topic_id)
        return

    # 2. Send completion text
    try:
        await tg_retry(
            bot.send_message,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
            text=VideoTemplates.topic_completed(day, total_days),
        )
    except Exception:
        logger.exception("Failed to send completion to topic_id=%d", topic_id)

    # 3. Change icon → ✅
    try:
        await tg_retry(
            bot.edit_forum_topic,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
            icon_custom_emoji_id=str(TOPIC_ICON_COMPLETED),
        )
    except Exception:
        logger.warning("Failed to change topic icon for topic_id=%d", topic_id)

    # 4. Close topic
    try:
        await tg_retry(
            bot.close_forum_topic,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
        )
    except Exception:
        logger.warning("Failed to close topic_id=%d", topic_id)


async def _send_late_warning_to_topic(
    bot: Bot,
    settings: Settings,
    topic_id: int,
    strike: int,
    max_strikes: int,
) -> None:
    """Send late warning message under the video in topic."""
    try:
        await tg_retry(
            bot.send_message,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
            text=VideoTemplates.topic_late_warning(strike, max_strikes),
        )
    except Exception:
        logger.exception("Failed to send late warning to topic_id=%d", topic_id)


async def _update_topic_name(
    bot: Bot,
    settings: Settings,
    topic_id: int,
    user: User,
    manager_repository: ManagerRepository,
    current_day: int,
    total_days: int,
) -> None:
    """Update topic name with current progress (e.g. 'Ivanova A. (Manager) 5/21')."""
    try:
        manager = await manager_repository.get_by_id(user.manager_id)
        manager_name = manager.name if manager else "?"
        name_parts = user.name.split() if user.name else []
        topic_title = OnboardingTemplates.topic_name(
            last_name=name_parts[0] if name_parts else "Unknown",
            first_name=name_parts[1] if len(name_parts) > 1 else "",
            patronymic=" ".join(name_parts[2:]) if len(name_parts) > 2 else None,
            manager_name=manager_name,
            current_day=current_day,
            total_days=total_days,
        )
        await tg_retry(
            bot.edit_forum_topic,
            chat_id=settings.kok_group_id,
            message_thread_id=topic_id,
            name=topic_title,
        )
    except Exception:
        logger.warning("Failed to update topic name for topic_id=%d", topic_id)


async def _edit_safe(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit message text, silently ignoring errors."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass
