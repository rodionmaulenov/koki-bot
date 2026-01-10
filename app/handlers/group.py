"""Команды менеджеров в группе."""

import logging
import secrets
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app import templates
from app.services.dashboard import DashboardService
from app.config import get_settings
from app.states import AddGirlStates, AddVideoStates
from app.utils.time_utils import format_date

logger = logging.getLogger(__name__)
router = Router()
settings = get_settings()


# =============================================================================
# /clear — очистить топик "Команды" (ПЕРВЫМ для перехвата FSM)
# =============================================================================

@router.message(
    Command("clear"),
    F.chat.id == settings.manager_group_id,
    F.message_thread_id == settings.commands_thread_id,
)
async def clear_command(message: Message, state: FSMContext, bot, commands_messages_service):
    """Удаляет сохранённые сообщения в топике, кроме правил."""

    # Сбрасываем FSM (если был в процессе /add или /add_video)
    await state.clear()

    # Удаляем сообщение с командой
    try:
        await message.delete()
    except Exception:
        pass

    # Получаем все сохранённые message_id
    message_ids = await commands_messages_service.get_all()

    if not message_ids:
        return

    # ID правил (не удаляем)
    rules_id = settings.rules_message_id

    for msg_id in message_ids:
        # Пропускаем правила
        if rules_id and msg_id == rules_id:
            continue

        try:
            await bot.delete_message(
                chat_id=message.chat.id,
                message_id=msg_id,
            )
        except Exception:
            # Сообщение уже удалено или нет прав
            pass

    # Очищаем таблицу
    await commands_messages_service.delete_all()


# =============================================================================
# /add — создание ссылки (FSM)
# =============================================================================

@router.message(
    Command("add"),
    F.chat.id == settings.manager_group_id,
    F.message_thread_id == settings.commands_thread_id,
)
async def add_command(message: Message, state: FSMContext, manager_service, commands_messages_service):
    """Начало диалога /add."""
    manager = await manager_service.get_by_telegram_id(message.from_user.id)
    if not manager:
        response = await message.reply(templates.MANAGER_NOT_FOUND)
        await commands_messages_service.add(response.message_id)
        return

    # Сохраняем manager_id в состояние
    await state.update_data(manager_id=manager["id"])
    await state.set_state(AddGirlStates.waiting_for_name)

    response = await message.reply("👩 Введи ФИО девушки:")
    await commands_messages_service.add(response.message_id)


@router.message(
    AddGirlStates.waiting_for_name,
    F.chat.id == settings.manager_group_id,
    F.message_thread_id == settings.commands_thread_id,
)
async def add_process_name(
    message: Message,
    state: FSMContext,
    user_service,
    course_service,
    bot,
    commands_messages_service,
):
    """Получили имя — создаём ссылку."""
    girl_name = message.text.strip()

    if not girl_name or len(girl_name.split()) < 3:
        response = await message.reply("❌ Введи полное ФИО (Фамилия Имя Отчество):")
        await commands_messages_service.add(response.message_id)
        return

    data = await state.get_data()
    manager_id = data["manager_id"]

    invite_code = secrets.token_urlsafe(8)

    # Проверяем, есть ли уже user с таким именем
    existing_user = await user_service.get_by_name_and_manager(girl_name, manager_id)

    if existing_user:
        # Проверяем, нет ли активного курса
        active_course = await course_service.get_active_by_user_id(existing_user["id"])
        if active_course and active_course.get("status") in ("setup", "active"):
            response = await message.reply(templates.MANAGER_USER_ALREADY_ON_COURSE)
            await commands_messages_service.add(response.message_id)
            await state.clear()
            return

        user = existing_user
    else:
        user = await user_service.create(
            name=girl_name,
            manager_id=manager_id,
        )

    try:
        course = await course_service.create(
            user_id=user["id"],
            invite_code=invite_code,
        )
    except ValueError:
        response = await message.reply(templates.MANAGER_USER_ALREADY_ON_COURSE)
        await commands_messages_service.add(response.message_id)
        await state.clear()
        return

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={course['invite_code']}"

    response = await message.reply(
        templates.MANAGER_LINK_CREATED.format(
            girl_name=girl_name,
            link=link,
        ),
        parse_mode="HTML",
    )
    await commands_messages_service.add(response.message_id)

    await state.clear()


# =============================================================================
# /add_video — разрешить обычное видео (FSM)
# =============================================================================

@router.message(
    Command("add_video"),
    F.chat.id == settings.manager_group_id,
    F.message_thread_id == settings.commands_thread_id,
)
async def add_video_command(message: Message, state: FSMContext, manager_service, commands_messages_service):
    """Начало диалога /add_video."""
    manager = await manager_service.get_by_telegram_id(message.from_user.id)
    if not manager:
        response = await message.reply(templates.MANAGER_NOT_FOUND)
        await commands_messages_service.add(response.message_id)
        return

    await state.update_data(manager_id=manager["id"])
    await state.set_state(AddVideoStates.waiting_for_name)

    response = await message.reply("👩 Введи ФИО девушки:")
    await commands_messages_service.add(response.message_id)


@router.message(
    AddVideoStates.waiting_for_name,
    F.chat.id == settings.manager_group_id,
    F.message_thread_id == settings.commands_thread_id,
)
async def add_video_process_name(
    message: Message,
    state: FSMContext,
    user_service,
    course_service,
    commands_messages_service,
):
    """Получили имя — разрешаем видео."""
    girl_name = message.text.strip()

    if not girl_name or len(girl_name) < 3:
        response = await message.reply("❌ Введи корректное ФИО (минимум 3 символа):")
        await commands_messages_service.add(response.message_id)
        return

    data = await state.get_data()
    manager_id = data["manager_id"]

    user = await user_service.get_by_name_and_manager(girl_name, manager_id)
    if not user:
        # Получаем список активных девушек
        active_users = await user_service.get_active_by_manager(manager_id)

        if active_users:
            names = "\n".join(f"• {u['name']}" for u in active_users)
            text = f"❌ Девушка «{girl_name}» не найдена.\n\n📋 Активные девушки:\n{names}"
        else:
            text = f"❌ Девушка «{girl_name}» не найдена.\n\nУ тебя нет активных девушек."

        response = await message.reply(text)
        await commands_messages_service.add(response.message_id)
        await state.clear()
        return

    course = await course_service.get_active_by_user_id(user["id"])
    if not course:
        response = await message.reply(templates.MANAGER_COURSE_NOT_FOUND)
        await commands_messages_service.add(response.message_id)
        await state.clear()
        return

    await course_service.update(course_id=course["id"], allow_video=True)

    response = await message.reply(templates.MANAGER_VIDEO_ALLOWED.format(girl_name=girl_name))
    await commands_messages_service.add(response.message_id)
    await state.clear()


# =============================================================================
# Callbacks для проверки видео (без изменений)
# =============================================================================

@router.callback_query(F.data.startswith("verify_ok_"))
async def verify_ok_callback(
    callback: CallbackQuery,
    course_service,
    user_service,
    manager_service,
    intake_logs_service,
    topic_service,
):
    """Менеджер принял видео."""
    await callback.answer()

    parts = callback.data.split("_")
    course_id = int(parts[2])
    day = int(parts[3])

    await intake_logs_service.update_status(
        course_id=course_id,
        day=day,
        status="taken",
        verified_by="manager",
    )

    course = await course_service.get_by_id(course_id)
    if not course:
        await callback.message.edit_text(templates.MANAGER_COURSE_NOT_FOUND)
        return

    user = await user_service.get_by_id(course["user_id"])
    if not user:
        await callback.message.edit_text(templates.MANAGER_USER_NOT_FOUND)
        return

    new_day = day + 1
    total_days = course.get("total_days") or 21

    if new_day > total_days:
        await course_service.update(course_id=course_id, status="completed", current_day=total_days)
    else:
        await course_service.update(course_id=course_id, current_day=new_day)

    topic_id = user.get("topic_id")
    if topic_id:
        manager = await manager_service.get_by_id(user["manager_id"])
        await topic_service.update_progress(
            topic_id=topic_id,
            girl_name=user.get("name", ""),
            manager_name=manager.get("name", "") if manager else "",
            completed_days=day,
            total_days=total_days,
        )

    await callback.message.edit_text(templates.MANAGER_VIDEO_APPROVED.format(day=day, total_days=total_days))


@router.callback_query(F.data.startswith("verify_no_"))
async def verify_no_callback(
    callback: CallbackQuery,
    course_service,
    user_service,
    manager_service,
    intake_logs_service,
    topic_service,
    bot,
    supabase,
):
    """Менеджер отклонил видео — программа завершена."""
    await callback.answer()

    parts = callback.data.split("_")
    course_id = int(parts[2])
    day = int(parts[3])

    await intake_logs_service.update_status(
        course_id=course_id,
        day=day,
        status="missed",
        verified_by="manager",
    )

    await course_service.update(course_id=course_id, status="refused")

    course = await course_service.get_by_id(course_id)
    total_days = course.get("total_days") or 21 if course else 21

    user = None
    if course:
        user = await user_service.get_by_id(course["user_id"])
        if user and user.get("telegram_id"):
            try:
                await bot.send_message(
                    chat_id=user["telegram_id"],
                    text=templates.VIDEO_REJECTED,
                )
            except Exception:
                pass

    # Закрываем топик с полной последовательностью
    topic_id = user.get("topic_id") if user else None
    if topic_id and course:
        manager = await manager_service.get_by_id(user["manager_id"])
        manager_name = manager.get("name", "") if manager else ""

        await topic_service.rename_topic_on_close(
            topic_id=topic_id,
            girl_name=user.get("name", ""),
            manager_name=manager_name,
            completed_days=day,
            total_days=total_days,
            status="refused",
        )

        if course.get("registration_message_id"):
            await topic_service.remove_registration_buttons(
                message_id=course["registration_message_id"],
                cycle_day=course.get("cycle_day", 1),
                intake_time=course.get("intake_time", ""),
                start_date=format_date(course.get("start_date", "")),
            )

        await topic_service.send_closure_message(
            topic_id=topic_id,
            status="refused",
            reason=templates.REFUSAL_REASON_VIDEO_REJECTED,
        )

        await topic_service.close_topic(topic_id)

    await callback.message.edit_text(templates.MANAGER_VIDEO_REJECTED.format(day=day, total_days=total_days))

    # Обновляем дашборд отказов
    dashboard_service = DashboardService(supabase, settings.manager_group_id)
    await dashboard_service.update_refusals(bot, settings.general_thread_id)


@router.callback_query(F.data.startswith("complete_"))
async def complete_course_callback(
    callback: CallbackQuery,
    course_service,
    user_service,
    manager_service,
    topic_service,
    bot,
):
    """Менеджер завершает курс досрочно."""
    await callback.answer()

    course_id = int(callback.data.split("_")[1])

    course = await course_service.get_by_id(course_id)
    if not course:
        await callback.message.edit_text(templates.MANAGER_COURSE_NOT_FOUND)
        return

    if course.get("status") != "active":
        await callback.message.edit_text("❌ Курс уже завершён.")
        return

    current_day = course.get("current_day", 1)
    total_days = course.get("total_days") or 21

    await course_service.update(course_id=course_id, status="completed")

    # Уведомляем девушку
    user = await user_service.get_by_id(course["user_id"])
    if user and user.get("telegram_id"):
        try:
            await bot.send_message(
                chat_id=user["telegram_id"],
                text=templates.COURSE_COMPLETED_EARLY,
            )
        except Exception:
            pass

    # Закрываем топик с полной последовательностью
    topic_id = user.get("topic_id") if user else None
    if topic_id:
        manager = await manager_service.get_by_id(user["manager_id"])
        manager_name = manager.get("name", "") if manager else ""

        await topic_service.rename_topic_on_close(
            topic_id=topic_id,
            girl_name=user.get("name", ""),
            manager_name=manager_name,
            completed_days=current_day,
            total_days=total_days,
            status="completed",
        )

        if course.get("registration_message_id"):
            await topic_service.remove_registration_buttons(
                message_id=course["registration_message_id"],
                cycle_day=course.get("cycle_day", 1),
                intake_time=course.get("intake_time", ""),
                start_date=format_date(course.get("start_date", "")),
            )

        await topic_service.send_closure_message(
            topic_id=topic_id,
            status="completed",
            reason="",
        )

        await topic_service.close_topic(topic_id)

    girl_name = user.get("name", "—") if user else "—"
    await callback.message.answer(
        templates.MANAGER_COURSE_COMPLETED.format(
            girl_name=girl_name,
            day=current_day,
            total_days=total_days,
        )
    )


@router.callback_query(F.data.startswith("extend_"))
async def extend_course_callback(
    callback: CallbackQuery,
    course_service,
    user_service,
    manager_service,
    topic_service,
    bot,
):
    """Менеджер продлевает курс на +21 день."""
    await callback.answer()

    course_id = int(callback.data.split("_")[1])

    course = await course_service.get_by_id(course_id)
    if not course:
        await callback.message.edit_text(templates.MANAGER_COURSE_NOT_FOUND)
        return

    if course.get("status") != "active":
        await callback.message.edit_text("❌ Курс не активен.")
        return

    current_total = course.get("total_days") or 21
    new_total = current_total + 21
    current_day = course.get("current_day", 1)

    await course_service.update(course_id=course_id, total_days=new_total)

    # Уведомляем девушку
    user = await user_service.get_by_id(course["user_id"])
    if user and user.get("telegram_id"):
        try:
            await bot.send_message(
                chat_id=user["telegram_id"],
                text=templates.COURSE_EXTENDED.format(total_days=new_total),
            )
        except Exception:
            pass

    # Обновляем название топика
    girl_name = user.get("name", "—") if user else "—"
    topic_id = user.get("topic_id") if user else None

    logger.info(f"Extend course: girl={girl_name}, topic_id={topic_id}, new_total={new_total}")

    if topic_id:
        manager = await manager_service.get_by_id(user["manager_id"])
        logger.info(f"Updating topic {topic_id} to {new_total} days")
        try:
            await topic_service.update_progress(
                topic_id=topic_id,
                girl_name=girl_name,
                manager_name=manager.get("name", "") if manager else "",
                completed_days=current_day - 1,
                total_days=new_total,
            )
            logger.info("Topic updated successfully")
        except Exception as e:
            logger.error(f"Failed to update topic: {e}")
    else:
        logger.warning(f"No topic_id for user {girl_name}")

    # Отправляем новое сообщение (не редактируем старое с кнопками)
    await callback.message.answer(
        templates.MANAGER_COURSE_EXTENDED.format(
            girl_name=girl_name,
            total_days=new_total,
        )
    )