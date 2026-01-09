"""Обработка видео-отчётов от девушек."""

from datetime import date, timedelta

from aiogram import Router, F
from aiogram.types import Message

from app.services.gemini import GeminiService
from app.utils.time_utils import get_tashkent_now, is_too_early
from app import templates

router = Router()

router.message.filter(F.chat.type == "private")


@router.message(F.video_note | F.video)
async def video_handler(
    message: Message,
    user_service,
    course_service,
    intake_logs_service,
    topic_service,
    manager_service,
    gemini_service: GeminiService,
    bot,
):
    """Девушка отправила видео (кружочек или обычное)."""

    # 1. Проверяем user
    user = await user_service.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(templates.ERROR_NO_USER)
        return

    # 2. Проверяем course
    course = await course_service.get_active_by_user_id(user["id"])
    if not course or course.get("status") != "active":
        await message.answer(templates.VIDEO_NO_ACTIVE_COURSE)
        return

    # 3. Проверяем что курс начался
    start_date_str = course.get("start_date")
    if start_date_str:
        today = get_tashkent_now().date()
        start_date = date.fromisoformat(start_date_str)

        if today < start_date:
            await message.answer(templates.VIDEO_COURSE_NOT_STARTED)
            return

        end_date = start_date + timedelta(days=20)
        if today > end_date:
            await message.answer(templates.VIDEO_COURSE_COMPLETED)
            return

    # 4. Определяем тип и file_id
    if message.video_note:
        file_id = message.video_note.file_id
        is_circle = True
    else:
        file_id = message.video.file_id
        is_circle = False

    # 5. Проверяем разрешение на обычное видео
    if not is_circle and not course.get("allow_video"):
        await message.answer(templates.VIDEO_ONLY_CIRCLES)
        return

    # 6. Проверяем что сегодня ещё не отправляла (только 1 видео в день)
    current_day = course.get("current_day", 1)
    existing_log = await intake_logs_service.get_by_course_and_day(
        course_id=course["id"],
        day=current_day,
    )
    if existing_log:
        await message.answer(templates.VIDEO_ALREADY_SENT)
        return

    # 7. Проверяем не слишком ли рано
    intake_time = course.get("intake_time", "12:00")
    too_early, window_start = is_too_early(intake_time)
    if too_early:
        await message.answer(templates.VIDEO_TOO_EARLY.format(window_start=window_start))
        return

    # 8. Скачиваем и проверяем видео
    async with GeminiService.download_video(bot, file_id) as video_path:
        result = await gemini_service.verify_video(video_path)

    # 9. Определяем статус
    is_confirmed = result["status"] == "confirmed"
    total_days = course.get("total_days") or 21

    if is_confirmed:
        log_status = "taken"
        response_text = templates.VIDEO_ACCEPTED.format(day=current_day, total_days=total_days)
    else:
        log_status = "pending_review"
        response_text = templates.VIDEO_PENDING_REVIEW

    # 10. Сохраняем в intake_logs
    await intake_logs_service.create(
        course_id=course["id"],
        day=current_day,
        status=log_status,
        video_file_id=file_id,
        verified_by="gemini" if is_confirmed else None,
        confidence=result["confidence"],
    )

    # 11. Отправляем в топик девушки
    topic_id = user.get("topic_id")
    if topic_id:
        await topic_service.send_video(
            topic_id=topic_id,
            video_file_id=file_id,
            day=current_day,
            total_days=total_days,
        )

        if not is_confirmed:
            await topic_service.send_review_buttons(
                topic_id=topic_id,
                course_id=course["id"],
                day=current_day,
                reason=result["reason"],
                total_days=total_days,
            )

    # 12. Если подтверждено — обновляем прогресс
    if is_confirmed:
        new_day = current_day + 1

        if new_day > total_days:
            await course_service.update(
                course_id=course["id"],
                status="completed",
                current_day=total_days,
            )
            response_text = templates.VIDEO_COURSE_FINISHED
            # Закрываем топик
            if topic_id:
                await topic_service.close_topic(topic_id)
        else:
            await course_service.update(
                course_id=course["id"],
                current_day=new_day,
            )

        if topic_id:
            manager = await manager_service.get_by_id(user["manager_id"])
            await topic_service.update_progress(
                topic_id=topic_id,
                girl_name=user.get("name", ""),
                manager_name=manager.get("name", "") if manager else "",
                completed_days=current_day,
                total_days=total_days,
            )

    await message.answer(response_text)