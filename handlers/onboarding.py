import asyncio
import logging
from datetime import date, time
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from dishka.integrations.aiogram import FromDishka

from callbacks.onboarding import OnboardingAction, OnboardingCallback
from config import Settings
from keyboards.card import card_keyboard
from keyboards.onboarding import (
    accept_terms_keyboard,
    cycle_day_keyboard,
    instructions_keyboard,
    intake_time_keyboard,
    rules_keyboard,
)
from models.enums import CourseStatus
from repositories.course_repository import CourseRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from states.onboarding import OnboardingStates
from templates import OnboardingTemplates
from utils.time import TASHKENT_TZ, get_tashkent_now

logger = logging.getLogger(__name__)

router = Router()

INVALID_AUTO_DELETE = 300  # 5 minutes for invalid links
USED_AUTO_DELETE = 30  # 30 seconds for "already used"
SPAM_AUTO_DELETE = 3  # 3 seconds for "use buttons" hint

# Topic icon for new registration
TOPIC_ICON_WAITING = 5235579393115438657  # ⭐

_TUTORIAL_VIDEO_PATH = Path(__file__).resolve().parent.parent / "assets" / "pill_square_optimized.mp4"


# ──────────────────────────────────────────────
# /start — entry point
# ──────────────────────────────────────────────


@router.message(CommandStart(), F.chat.type == "private")
async def on_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    manager_repository: FromDishka[ManagerRepository],
) -> None:
    invite_code = command.args.strip() if command.args else ""

    if not invite_code:
        manager = await manager_repository.get_by_telegram_id(message.from_user.id)
        if manager and manager.role == "manager":
            await message.answer(OnboardingTemplates.manager_greeting(manager.name))
            return
        if manager and manager.role == "accountant":
            await message.answer(OnboardingTemplates.accountant_greeting(manager.name))
            return
        await _send_and_auto_delete(message, OnboardingTemplates.no_link(), INVALID_AUTO_DELETE)
        return

    try:
        course = await course_repository.get_by_invite_code(invite_code)
    except Exception:
        logger.exception("DB error looking up invite_code=%s", invite_code)
        await _send_and_auto_delete(message, OnboardingTemplates.invalid_link(), INVALID_AUTO_DELETE)
        return

    if course is None:
        await _send_and_auto_delete(message, OnboardingTemplates.invalid_link(), INVALID_AUTO_DELETE)
        return

    if course.invite_used:
        await _send_and_auto_delete(message, OnboardingTemplates.link_used(), USED_AUTO_DELETE)
        return

    if course.status == CourseStatus.EXPIRED:
        date_str = course.created_at.astimezone(TASHKENT_TZ).date().strftime("%d.%m.%Y")
        await _send_and_auto_delete(message, OnboardingTemplates.link_expired(date_str), INVALID_AUTO_DELETE)
        return

    # Check date expiration
    expired = await _check_and_expire(course, course_repository)
    if expired:
        date_str = course.created_at.astimezone(TASHKENT_TZ).date().strftime("%d.%m.%Y")
        await _send_and_auto_delete(message, OnboardingTemplates.link_expired(date_str), INVALID_AUTO_DELETE)
        return

    if course.status != CourseStatus.SETUP:
        await _send_and_auto_delete(message, OnboardingTemplates.invalid_link(), INVALID_AUTO_DELETE)
        return

    # Check if another user already started with this link
    try:
        user = await user_repository.get_by_id(course.user_id)
    except Exception:
        logger.exception("DB error fetching user_id=%d", course.user_id)
        await _send_and_auto_delete(message, OnboardingTemplates.invalid_link(), INVALID_AUTO_DELETE)
        return

    if user is None:
        await _send_and_auto_delete(message, OnboardingTemplates.invalid_link(), INVALID_AUTO_DELETE)
        return

    tg_id = message.from_user.id

    if user.telegram_id is not None and user.telegram_id != tg_id:
        # Another person already claimed this link
        await _send_and_auto_delete(message, OnboardingTemplates.invalid_link(), INVALID_AUTO_DELETE)
        return

    # Save telegram_id if not set yet
    if user.telegram_id is None:
        try:
            await user_repository.set_telegram_id(user.id, tg_id)
        except Exception:
            logger.exception("Failed to set telegram_id for user_id=%d", user.id)
            await _send_and_auto_delete(message, OnboardingTemplates.invalid_link(), INVALID_AUTO_DELETE)
            return

    # Check if girl is already in onboarding (re-clicked link)
    current_state = await state.get_state()
    if current_state and current_state.startswith("OnboardingStates:"):
        data = await state.get_data()
        if data.get("course_id") == course.id:
            # Same course — resend current step
            await _resend_current_step(message, state, current_state, data)
            return

    # Start onboarding — go directly to instructions
    sent = await message.answer(
        OnboardingTemplates.instructions(),
        reply_markup=instructions_keyboard(),
    )
    await state.set_state(OnboardingStates.instructions)
    course_date = course.created_at.astimezone(TASHKENT_TZ).date().isoformat()
    await state.update_data(
        course_id=course.id,
        user_id=user.id,
        manager_id=user.manager_id,
        user_name=user.name,
        bot_message_id=sent.message_id,
        course_created_date=course_date,
    )
    logger.info(
        "Onboarding started: invite_code=%s, course_id=%d, tg_id=%d",
        invite_code, course.id, tg_id,
    )


# ──────────────────────────────────────────────
# Step 1: Instructions → "Понятно"
# ──────────────────────────────────────────────


@router.callback_query(
    OnboardingStates.instructions,
    OnboardingCallback.filter(F.action == OnboardingAction.UNDERSTOOD),
)
async def on_instructions_understood(
    callback: CallbackQuery,
    state: FSMContext,
    course_repository: FromDishka[CourseRepository],
) -> None:
    if await _check_expiration_callback(callback, state, course_repository):
        return

    await callback.message.edit_text(
        OnboardingTemplates.cycle_day(),
        reply_markup=cycle_day_keyboard(),
    )
    await state.set_state(OnboardingStates.cycle_day)
    await callback.answer()


# ──────────────────────────────────────────────
# Step 2: Cycle day (1-4)
# ──────────────────────────────────────────────


@router.callback_query(
    OnboardingStates.cycle_day,
    OnboardingCallback.filter(F.action == OnboardingAction.CYCLE_DAY),
)
async def on_cycle_day_selected(
    callback: CallbackQuery,
    callback_data: OnboardingCallback,
    state: FSMContext,
    course_repository: FromDishka[CourseRepository],
) -> None:
    if await _check_expiration_callback(callback, state, course_repository):
        return

    cycle_day = int(callback_data.value)
    await state.update_data(cycle_day=cycle_day)

    keyboard = intake_time_keyboard()
    if not keyboard.inline_keyboard:
        # Too late — no time slots left today
        await callback.answer(OnboardingTemplates.no_slots_left(), show_alert=True)
        return

    await callback.message.edit_text(
        OnboardingTemplates.intake_time(),
        reply_markup=keyboard,
    )
    await state.set_state(OnboardingStates.intake_time)
    await callback.answer()


# ──────────────────────────────────────────────
# Step 3: Intake time → Rules
# ──────────────────────────────────────────────


@router.callback_query(
    OnboardingStates.intake_time,
    OnboardingCallback.filter(F.action == OnboardingAction.TIME),
)
async def on_time_selected(
    callback: CallbackQuery,
    callback_data: OnboardingCallback,
    state: FSMContext,
    course_repository: FromDishka[CourseRepository],
) -> None:
    if await _check_expiration_callback(callback, state, course_repository):
        return

    # Callback value uses "-" instead of ":" (separator conflict)
    intake_time_str = callback_data.value.replace("-", ":")
    start_date_str = get_tashkent_now().date().strftime("%d.%m.%Y")
    await state.update_data(intake_time=intake_time_str, start_date=start_date_str)

    await callback.message.edit_text(
        OnboardingTemplates.rules(intake_time_str, start_date_str),
        reply_markup=rules_keyboard(),
    )
    await state.set_state(OnboardingStates.rules)
    await callback.answer()


# ──────────────────────────────────────────────
# Step 4: Rules → "Понятно" → Bot instructions (new message)
# ──────────────────────────────────────────────


@router.callback_query(
    OnboardingStates.rules,
    OnboardingCallback.filter(F.action == OnboardingAction.RULES_OK),
)
async def on_rules_ok(
    callback: CallbackQuery,
    state: FSMContext,
    course_repository: FromDishka[CourseRepository],
) -> None:
    if await _check_expiration_callback(callback, state, course_repository):
        return

    # Remove button from rules message (message_1)
    await callback.message.edit_reply_markup(reply_markup=None)

    # Send new message (message_2) with bot instructions
    sent = await callback.message.answer(
        OnboardingTemplates.bot_instructions(),
        reply_markup=accept_terms_keyboard(),
    )
    await state.update_data(instructions_message_id=sent.message_id)
    await state.set_state(OnboardingStates.accept_terms)
    await callback.answer()


# ──────────────────────────────────────────────
# Step 5: Accept terms → Finalization
# ──────────────────────────────────────────────


@router.callback_query(
    OnboardingStates.accept_terms,
    OnboardingCallback.filter(F.action == OnboardingAction.ACCEPT),
)
async def on_accept_terms(
    callback: CallbackQuery,
    state: FSMContext,
    settings: FromDishka[Settings],
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
    manager_repository: FromDishka[ManagerRepository],
) -> None:
    # Remove button IMMEDIATELY to prevent double-click
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    if await _check_expiration_callback(callback, state, course_repository):
        return

    data = await state.get_data()

    try:
        course_id = data["course_id"]
        user_id = data["user_id"]
        manager_id = data["manager_id"]
        user_name = data["user_name"]
        cycle_day = data["cycle_day"]
        intake_time_str = data["intake_time"]
        bot_message_id = data["bot_message_id"]
    except KeyError:
        logger.exception("Missing FSM data in on_accept_terms")
        await callback.answer(OnboardingTemplates.error_try_again(), show_alert=True)
        await state.clear()
        return

    # Parse time
    try:
        h, m = intake_time_str.split(":")
        intake_time_obj = time(hour=int(h), minute=int(m))
    except (ValueError, TypeError):
        logger.error("Invalid intake_time in FSM data: %r", intake_time_str)
        await callback.answer(OnboardingTemplates.error_try_again(), show_alert=True)
        await state.clear()
        return
    today = get_tashkent_now().date()

    # 1. Activate course in DB (atomic — only one click wins)
    try:
        activated = await course_repository.activate(
            course_id=course_id,
            cycle_day=cycle_day,
            intake_time=intake_time_obj,
            start_date=today,
        )
    except Exception:
        logger.exception("Failed to activate course_id=%d", course_id)
        await callback.answer(OnboardingTemplates.error_try_again(), show_alert=True)
        return

    if not activated:
        # Race condition: another click already activated — just finish silently
        logger.debug("Course already activated by concurrent click: course_id=%d", course_id)
        await state.clear()
        await callback.answer()
        return

    # 2. Get manager name for topic
    manager_name = "Manager"
    try:
        manager = await manager_repository.get_by_id(manager_id)
        if manager:
            manager_name = manager.name
    except Exception:
        logger.exception("Failed to get manager_id=%d", manager_id)

    # Parse name parts for topic
    name_parts = user_name.split() if user_name else []
    last_name = name_parts[0] if name_parts else "Unknown"
    first_name = name_parts[1] if len(name_parts) > 1 else ""
    patronymic = " ".join(name_parts[2:]) if len(name_parts) > 2 else None

    topic_title = OnboardingTemplates.topic_name(
        last_name=last_name,
        first_name=first_name,
        patronymic=patronymic,
        manager_name=manager_name,
        current_day=0,
        total_days=21,
    )

    # 3. Create topic in KOK group
    bot = callback.bot
    try:
        topic = await bot.create_forum_topic(
            chat_id=settings.kok_group_id,
            name=topic_title,
            icon_custom_emoji_id=str(TOPIC_ICON_WAITING),
        )
        topic_id = topic.message_thread_id
    except TelegramBadRequest:
        logger.warning("Failed to create topic with icon, retrying without")
        try:
            topic = await bot.create_forum_topic(
                chat_id=settings.kok_group_id,
                name=topic_title,
            )
            topic_id = topic.message_thread_id
        except Exception:
            logger.exception("Retry failed for course_id=%d", course_id)
            topic_id = 0
    except Exception:
        logger.exception("Failed to create forum topic for course_id=%d", course_id)
        topic_id = 0

    # 4. Send registration card to topic
    tg_user = callback.from_user
    start_date_str = today.strftime("%d.%m.%Y")

    card_text = OnboardingTemplates.registration_card(
        full_name=user_name,
        cycle_day=cycle_day,
        intake_time_str=intake_time_str,
        start_date_str=start_date_str,
        telegram_username=tg_user.username,
        telegram_id=tg_user.id,
    )

    registration_message_id = 0
    if topic_id:
        try:
            card_msg = await bot.send_message(
                chat_id=settings.kok_group_id,
                message_thread_id=topic_id,
                text=card_text,
                reply_markup=card_keyboard(course_id, can_extend=True),
            )
            registration_message_id = card_msg.message_id
        except Exception:
            logger.exception("Failed to send registration card to topic_id=%d", topic_id)

    # 5. Update DB with topic_id and registration_message_id
    if topic_id:
        try:
            await user_repository.set_topic_id(user_id, topic_id)
        except Exception:
            logger.exception("Failed to set topic_id for user_id=%d", user_id)

    if registration_message_id:
        try:
            await course_repository.set_registration_message_id(course_id, registration_message_id)
        except Exception:
            logger.exception("Failed to set registration_message_id for course_id=%d", course_id)

    # Send tutorial video (message_3)
    video_msg = None
    try:
        video_msg = await callback.message.answer_video(
            video=FSInputFile(_TUTORIAL_VIDEO_PATH),
            caption=OnboardingTemplates.tutorial_video_caption(),
        )
    except Exception:
        logger.exception("Failed to send tutorial video")
        if video_msg is None:
            try:
                video_msg = await callback.message.answer(
                    OnboardingTemplates.tutorial_video_caption(),
                )
            except Exception:
                logger.exception("Failed to send tutorial video caption fallback")

    await state.clear()
    await callback.answer()

    logger.info(
        "Onboarding completed: course_id=%d, user_id=%d, topic_id=%d",
        course_id, user_id, topic_id,
    )


# ──────────────────────────────────────────────
# Spam handler — any message during onboarding
# ──────────────────────────────────────────────


@router.message(OnboardingStates.instructions, F.chat.type == "private")
@router.message(OnboardingStates.cycle_day, F.chat.type == "private")
@router.message(OnboardingStates.intake_time, F.chat.type == "private")
@router.message(OnboardingStates.rules, F.chat.type == "private")
@router.message(OnboardingStates.accept_terms, F.chat.type == "private")
async def on_spam_during_onboarding(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    except Exception:
        logger.debug("Failed to delete spam message_id=%d", message.message_id)

    sent = await message.answer(OnboardingTemplates.use_buttons())
    _schedule_auto_delete(message.bot, message.chat.id, sent.message_id, SPAM_AUTO_DELETE)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


async def _check_and_expire(course, course_repository: CourseRepository) -> bool:
    """Check if course is expired by date. Returns True if expired."""
    course_date = course.created_at.astimezone(TASHKENT_TZ).date()
    today = get_tashkent_now().date()

    if course_date == today:
        return False

    if course.status == CourseStatus.SETUP:
        try:
            await course_repository.set_expired(course.id)
        except Exception:
            logger.exception("Failed to expire course_id=%d", course.id)

    return True


async def _check_expiration_callback(
    callback: CallbackQuery,
    state: FSMContext,
    course_repository: CourseRepository,
) -> bool:
    """Check expiration on every callback step. Returns True if expired."""
    data = await state.get_data()
    course_id = data.get("course_id")
    course_date_str = data.get("course_created_date")

    if not course_id or not course_date_str:
        await callback.answer(OnboardingTemplates.session_expired(), show_alert=True)
        await state.clear()
        return True

    today = get_tashkent_now().date()
    course_date = date.fromisoformat(course_date_str)

    if course_date == today:
        return False

    # Link expired — set status in DB
    try:
        await course_repository.set_expired(course_id)
    except Exception:
        logger.exception("Failed to expire course_id=%d", course_id)

    date_str = course_date.strftime("%d.%m.%Y")
    try:
        await callback.message.edit_text(OnboardingTemplates.link_expired(date_str))
    except TelegramBadRequest:
        pass
    await state.clear()
    await callback.answer()
    return True


async def _resend_current_step(
    message: Message,
    state: FSMContext,
    current_state: str,
    data: dict,
) -> None:
    """Resend the current onboarding step when girl re-clicks the link."""
    state_name = current_state.split(":")[-1]
    bot_message_id = data.get("bot_message_id")

    # accept_terms has separate logic (message_2, not message_1)
    if state_name == "accept_terms":
        instructions_msg_id = data.get("instructions_message_id")
        if instructions_msg_id:
            try:
                await message.bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=instructions_msg_id,
                    reply_markup=accept_terms_keyboard(),
                )
                return
            except TelegramBadRequest:
                pass
        sent = await message.answer(
            OnboardingTemplates.bot_instructions(),
            reply_markup=accept_terms_keyboard(),
        )
        await state.update_data(instructions_message_id=sent.message_id)
        return

    # Determine text and keyboard for current step
    time_kb = intake_time_keyboard()

    if state_name == "intake_time" and not time_kb.inline_keyboard:
        # No slots left — roll back to cycle_day so she can retry tomorrow
        await state.set_state(OnboardingStates.cycle_day)
        text = OnboardingTemplates.cycle_day()
        keyboard = cycle_day_keyboard()
    elif state_name == "intake_time":
        text = OnboardingTemplates.intake_time()
        keyboard = time_kb
    else:
        state_to_text = {
            "instructions": (OnboardingTemplates.instructions(), instructions_keyboard()),
            "cycle_day": (OnboardingTemplates.cycle_day(), cycle_day_keyboard()),
            "rules": (
                OnboardingTemplates.rules(
                    data.get("intake_time", ""),
                    data.get("start_date", ""),
                ),
                rules_keyboard(),
            ),
        }
        if state_name not in state_to_text:
            return
        text, keyboard = state_to_text[state_name]

    if bot_message_id:
        try:
            await message.bot.edit_message_text(
                text=text,
                chat_id=message.chat.id,
                message_id=bot_message_id,
                reply_markup=keyboard,
            )
            return
        except TelegramBadRequest:
            pass

    # Fallback: send new message
    sent = await message.answer(text, reply_markup=keyboard)
    await state.update_data(bot_message_id=sent.message_id)


async def _send_and_auto_delete(message: Message, text: str, delay: int) -> None:
    """Send a message and schedule auto-deletion."""
    sent = await message.answer(text)
    _schedule_auto_delete(message.bot, message.chat.id, sent.message_id, delay)


def _schedule_auto_delete(bot, chat_id: int, message_id: int, delay: int) -> None:
    """Schedule a message for auto-deletion."""
    asyncio.create_task(_auto_delete(bot, chat_id, message_id, delay))


async def _auto_delete(bot, chat_id: int, message_id: int, delay: int) -> None:
    try:
        await asyncio.sleep(delay)
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass
    except Exception:
        logger.debug("Auto-delete failed: chat_id=%d, message_id=%d", chat_id, message_id)


@router.callback_query(OnboardingCallback.filter())
async def on_expired_callback(callback: CallbackQuery) -> None:
    """Catch-all for expired onboarding buttons (FSM state gone)."""
    await callback.answer(
        OnboardingTemplates.link_expired_contact_manager(), show_alert=True,
    )
