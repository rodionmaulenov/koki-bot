import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka
from redis.asyncio import Redis

from callbacks.menu import MenuAction, MenuCallback
from models.ocr import OCRServerError
from repositories.course_repository import CourseRepository
from repositories.user_repository import UserRepository
from services.ocr_service import OCRService
from states.add import AddStates
from templates import AddTemplates
from topic_access.message_middleware import ADD_ACTIVE_KEY_PREFIX
from utils.message import delete_user_message, edit_or_send, extract_image_file_id
from utils.time import get_tashkent_now
from utils.validators import validate_passport_name

logger = logging.getLogger(__name__)

router = Router()

EVENING_CUTOFF_HOUR = 20


def _validate_birth_date(raw: str | None) -> str | None:
    """Validate DD.MM.YYYY format. Returns normalized string or None."""
    if not raw:
        return None
    try:
        parsed = datetime.strptime(raw, "%d.%m.%Y")
        return parsed.strftime("%d.%m.%Y")
    except ValueError:
        logger.debug("Invalid birth_date from OCR: %s", raw)
        return None


@router.callback_query(MenuCallback.filter(F.action == MenuAction.ADD))
async def on_add_start(
    callback: CallbackQuery,
    state: FSMContext,
    redis: FromDishka[Redis],
) -> None:
    now = get_tashkent_now()
    if now.hour >= EVENING_CUTOFF_HOUR:
        await callback.answer(AddTemplates.time_restricted(), show_alert=True)
        return

    await callback.answer()
    await state.clear()

    thread_id = callback.message.message_thread_id
    if thread_id:
        await redis.set(
            f"{ADD_ACTIVE_KEY_PREFIX}:{thread_id}",
            callback.from_user.id,
            ex=3600,
        )

    sent = await callback.message.answer(
        text=AddTemplates.ask_passport(),
    )

    await state.set_state(AddStates.waiting_passport)
    await state.update_data(bot_message_id=sent.message_id)


@router.message(AddStates.waiting_passport, F.photo)
async def on_passport_photo(
    message: Message,
    state: FSMContext,
    ocr_service: FromDishka[OCRService],
    user_repository: FromDishka[UserRepository],
    course_repository: FromDishka[CourseRepository],
    redis: FromDishka[Redis],
) -> None:
    await _handle_passport_file(
        message, state, message.photo[-1].file_id,
        ocr_service, user_repository, course_repository, redis,
    )


@router.message(AddStates.waiting_passport, F.document)
async def on_passport_document(
    message: Message,
    state: FSMContext,
    ocr_service: FromDishka[OCRService],
    user_repository: FromDishka[UserRepository],
    course_repository: FromDishka[CourseRepository],
    redis: FromDishka[Redis],
) -> None:
    file_id = await extract_image_file_id(
        message, state, AddTemplates.photo_only(),
    )
    if file_id is None:
        return
    await _handle_passport_file(
        message, state, file_id,
        ocr_service, user_repository, course_repository, redis,
    )


async def _handle_passport_file(
    message: Message,
    state: FSMContext,
    file_id: str,
    ocr_service: OCRService,
    user_repository: UserRepository,
    course_repository: CourseRepository,
    redis: Redis,
) -> None:
    data = await state.get_data()
    bot_message_id = data.get("bot_message_id")

    await delete_user_message(message)
    await state.update_data(passport_file_id=file_id)

    await edit_or_send(
        message, state, bot_message_id,
        text=AddTemplates.ask_passport_processing(),
    )

    # Re-read bot_message_id in case edit_or_send created a new message
    data = await state.get_data()
    bot_message_id = data.get("bot_message_id")

    try:
        result = await ocr_service.process_passport(file_id)
    except OCRServerError:
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.ocr_server_error(),
        )
        return

    if not result.is_document:
        logger.info("Not a passport, file_id=%s", file_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.not_a_passport(),
        )
        return

    if result.first_name and result.last_name:
        parts = [result.last_name, result.first_name]
        if result.patronymic:
            parts.append(result.patronymic)
        raw_name = " ".join(parts)

        name = validate_passport_name(raw_name)
        if name:
            birth_date = _validate_birth_date(result.birth_date)

            await edit_or_send(
                message, state, bot_message_id,
                text=AddTemplates.ocr_passport_result(name),
            )
            await state.update_data(name=name, birth_date=birth_date)
            logger.info("Passport OCR success: %s, birth_date=%s", name, birth_date)

            # Re-read bot_message_id in case edit_or_send created a new message
            data = await state.get_data()
            bot_message_id = data.get("bot_message_id")

            # Dedup: check if user with same last_name + first_name + birth_date exists
            if birth_date:
                try:
                    existing = await user_repository.get_by_name_prefix_and_birth_date(
                        result.last_name.strip(), result.first_name.strip(), birth_date,
                    )
                    if existing:
                        # Check if user already has an active course
                        active_course = await course_repository.get_active_by_user_id(
                            existing.id,
                        )
                        if active_course:
                            logger.info(
                                "Blocked: user_id=%d already has active course_id=%d (status=%s)",
                                existing.id, active_course.id, active_course.status,
                            )
                            await edit_or_send(
                                message, state, bot_message_id,
                                text=AddTemplates.user_has_active_course(),
                            )
                            thread_id = message.message_thread_id
                            if thread_id:
                                try:
                                    await redis.delete(f"{ADD_ACTIVE_KEY_PREFIX}:{thread_id}")
                                except Exception:
                                    pass
                            await state.clear()
                            return

                        await state.update_data(existing_user_id=existing.id)
                        logger.info(
                            "Dedup: found existing user_id=%d for %s (%s)",
                            existing.id, name, birth_date,
                        )
                except Exception:
                    logger.exception("Dedup lookup failed for %s", name)

            # Success → NEW message for receipt step
            sent = await message.answer(text=AddTemplates.ask_receipt())
            await state.update_data(bot_message_id=sent.message_id)
            await state.set_state(AddStates.waiting_receipt)
            return

    logger.info("Passport OCR failed or invalid, file_id=%s", file_id)
    await edit_or_send(
        message, state, bot_message_id,
        text=AddTemplates.ocr_passport_bad_photo(),
    )


@router.message(AddStates.waiting_passport)
async def on_passport_unsupported(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await delete_user_message(message)
    await edit_or_send(
        message, state, data.get("bot_message_id"),
        text=AddTemplates.photo_only(),
    )