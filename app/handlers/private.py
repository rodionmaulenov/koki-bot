"""Личные сообщения от девушек."""
from datetime import timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject

from app.keyboards import cycle_day_keyboard, time_keyboard_today, time_keyboard, understand_button
from app.utils.time_utils import get_tashkent_now, format_date, is_created_today
from app import templates

router = Router()

router.message.filter(F.chat.type == "private")


@router.message(CommandStart(deep_link=True))
async def start_with_link(
        message: Message,
        command: CommandObject,
        course_service,
        user_service,
):
    invite_code = command.args

    course = await course_service.get_by_invite_code(invite_code)

    if not course:
        await message.answer(templates.LINK_INVALID)
        return

    if course.get("invite_used"):
        await message.answer(templates.LINK_USED)
        return

    await user_service.set_telegram_id(
        user_id=course["user_id"],
        telegram_id=message.from_user.id,
    )

    await course_service.mark_invite_used(course["id"])

    user = await user_service.get_by_id(course["user_id"])
    girl_name = user.get("name", "")

    await message.answer(
        templates.WELCOME.format(girl_name=girl_name),
        reply_markup=understand_button(),
    )


@router.callback_query(F.data == "understand")
async def understand_callback(
        callback: CallbackQuery,
        user_service,
        course_service,
):
    await callback.answer()

    user = await user_service.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.edit_text(templates.ERROR_NO_USER)
        return

    course = await course_service.get_active_by_user_id(user["id"])
    if not course:
        await callback.message.edit_text(templates.ERROR_NO_COURSE)
        return

    # Проверяем что курс создан сегодня
    if not is_created_today(course.get("created_at", "")):
        await course_service.set_expired(course["id"])
        await callback.message.edit_text(templates.TOO_LATE_REGISTRATION_EXPIRED)
        return

    await callback.message.delete()
    await callback.message.answer(
        templates.SELECT_CYCLE_DAY,
        reply_markup=cycle_day_keyboard(),
    )

@router.callback_query(F.data.startswith("cycle_"))
async def cycle_day_callback(
        callback: CallbackQuery,
        course_service,
        user_service,
):
    await callback.answer()

    cycle_day = int(callback.data.split("_")[1])

    user = await user_service.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.edit_text(templates.ERROR_NO_USER)
        return

    course = await course_service.get_active_by_user_id(user["id"])
    if not course:
        await callback.message.edit_text(templates.ERROR_NO_COURSE)
        return

    # Проверяем что курс создан сегодня
    if not is_created_today(course.get("created_at", "")):
        await course_service.set_expired(course["id"])
        await callback.message.edit_text(templates.TOO_LATE_REGISTRATION_EXPIRED)
        return

    now = get_tashkent_now()

    if cycle_day == 4:
        keyboard = time_keyboard_today()

        if keyboard is None:
            # Слишком поздно — показываем сообщение без кнопок
            await callback.message.edit_text(templates.TOO_LATE_TODAY)
            return

        start_date = now.date()
        text = templates.CYCLE_DAY_TODAY.format(cycle_day=cycle_day)
    else:
        start_date = (now + timedelta(days=1)).date()
        keyboard = time_keyboard()
        text = templates.CYCLE_DAY_TOMORROW.format(cycle_day=cycle_day)

    await course_service.update(
        course_id=course["id"],
        cycle_day=cycle_day,
        start_date=start_date.isoformat(),
    )

    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("time_"))
async def time_callback(
        callback: CallbackQuery,
        course_service,
        user_service,
        manager_service,
        topic_service,
):
    await callback.answer()

    user = await user_service.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.edit_text(templates.ERROR_NO_USER)
        return

    course = await course_service.get_active_by_user_id(user["id"])
    if not course:
        await callback.message.edit_text(templates.ERROR_NO_COURSE)
        return

    # Проверяем что курс создан сегодня
    if not is_created_today(course.get("created_at", "")):
        await course_service.set_expired(course["id"])
        await callback.message.edit_text(templates.TOO_LATE_REGISTRATION_EXPIRED)
        return

    parts = callback.data.split("_")
    hour = int(parts[1])
    minute = int(parts[2])
    intake_time = f"{hour:02d}:{minute:02d}"

    await course_service.update(
        course_id=course["id"],
        intake_time=intake_time,
        status="active",
        current_day=1,
    )

    manager = await manager_service.get_by_id(user["manager_id"])
    manager_name = manager.get("name", "") if manager else ""

    topic_id = await topic_service.create_topic(
        girl_name=user.get("name", ""),
        manager_name=manager_name,
    )

    start_date = format_date(course.get("start_date", ""))

    if topic_id:
        await user_service.set_topic_id(user["id"], topic_id)

        message_id = await topic_service.send_registration_info(
            topic_id=topic_id,
            course_id=course["id"],
            cycle_day=course.get("cycle_day", 1),
            intake_time=intake_time,
            start_date=start_date,
        )

        if message_id:
            await course_service.update(
                course_id=course["id"],
                registration_message_id=message_id,
            )

    text = templates.REGISTRATION_COMPLETE.format(
        start_date=start_date,
        intake_time=intake_time,
    )

    await callback.message.edit_text(text)


@router.message(CommandStart())
async def start_without_link(message: Message, user_service, course_service):
    user = await user_service.get_by_telegram_id(message.from_user.id)

    if user:
        course = await course_service.get_active_by_user_id(user["id"])
        if course and course.get("status") == "active":
            await message.answer(
                templates.ALREADY_ON_COURSE.format(
                    girl_name=user.get("name", ""),
                    current_day=course.get("current_day", 1),
                    total_days=course.get("total_days") or 21,
                    intake_time=course.get("intake_time", "—"),
                )
            )
            return

    await message.answer(templates.ASK_MANAGER_FOR_LINK)