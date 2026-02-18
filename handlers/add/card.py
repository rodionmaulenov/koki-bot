import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import InputMediaPhoto, Message
from dishka.integrations.aiogram import FromDishka
from redis.asyncio import Redis

from keyboards.payment import payment_receipt_keyboard
from models.ocr import OCRServerError
from repositories.manager_repository import ManagerRepository
from services.add_service import AddService
from services.ocr_service import OCRService
from states.add import AddStates
from templates import AddTemplates
from topic_access.message_middleware import ADD_ACTIVE_KEY_PREFIX
from utils.message import delete_user_message, edit_or_send, extract_image_file_id
from utils.validators import validate_card_input

logger = logging.getLogger(__name__)

router = Router()


@router.message(AddStates.waiting_card, F.photo)
async def on_card_photo(
    message: Message,
    state: FSMContext,
    ocr_service: FromDishka[OCRService],
    add_service: FromDishka[AddService],
    manager_repository: FromDishka[ManagerRepository],
    redis: FromDishka[Redis],
) -> None:
    await _handle_card_file(
        message, state, message.photo[-1].file_id,
        ocr_service, add_service, manager_repository, redis,
    )


@router.message(AddStates.waiting_card, F.document)
async def on_card_document(
    message: Message,
    state: FSMContext,
    ocr_service: FromDishka[OCRService],
    add_service: FromDishka[AddService],
    manager_repository: FromDishka[ManagerRepository],
    redis: FromDishka[Redis],
) -> None:
    file_id = await extract_image_file_id(
        message, state, AddTemplates.photo_only(),
    )
    if file_id is None:
        return
    await _handle_card_file(
        message, state, file_id,
        ocr_service, add_service, manager_repository, redis,
    )


async def _handle_card_file(
    message: Message,
    state: FSMContext,
    file_id: str,
    ocr_service: OCRService,
    add_service: AddService,
    manager_repository: ManagerRepository,
    redis: Redis,
) -> None:
    data = await state.get_data()

    await delete_user_message(message)

    bot_message_id = data.get("bot_message_id")
    await state.update_data(card_file_id=file_id)

    await edit_or_send(
        message, state, bot_message_id,
        text=AddTemplates.ask_card_processing(),
    )

    # Re-read bot_message_id in case edit_or_send created a new message
    data = await state.get_data()
    bot_message_id = data.get("bot_message_id")

    try:
        result = await ocr_service.process_card(file_id)
    except OCRServerError:
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.ocr_server_error(),
        )
        return

    if not result.is_document:
        logger.info("Not a card, file_id=%s", file_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.not_a_card(),
        )
        return

    if not result or not result.card_number or not result.card_holder:
        logger.info("Card OCR failed or invalid, asking for new photo")
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.ocr_card_bad_photo(),
        )
        return

    combined = f"{result.card_number} {result.card_holder}"
    validated = validate_card_input(combined)
    if not validated:
        logger.info("Card OCR validation failed, asking for new photo")
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.ocr_card_bad_photo(),
        )
        return

    card_number, card_holder = validated
    await state.update_data(card_number=card_number, card_holder=card_holder)
    logger.info("Card OCR success: %s %s", card_number, card_holder)

    # Show OCR result
    await edit_or_send(
        message, state, bot_message_id,
        text=AddTemplates.ocr_card_result(card_number, card_holder),
    )

    # Create link immediately
    await _create_link(message, state, add_service, manager_repository, redis)


async def _clear_add_flow_key(redis: Redis, thread_id: int | None) -> None:
    if thread_id:
        try:
            await redis.delete(f"{ADD_ACTIVE_KEY_PREFIX}:{thread_id}")
        except Exception:
            pass


async def _create_link(
    message: Message,
    state: FSMContext,
    add_service: AddService,
    manager_repository: ManagerRepository,
    redis: Redis,
) -> None:
    data = await state.get_data()

    required_keys = (
        "name", "passport_file_id", "receipt_file_id",
        "receipt_price", "card_file_id", "card_number", "card_holder",
    )
    if not all(key in data for key in required_keys):
        logger.error("FSM data expired, missing keys: %s", message.from_user.id)
        await message.answer(text=AddTemplates.error_try_later())
        await _clear_add_flow_key(redis, message.message_thread_id)
        await state.clear()
        return

    manager = await manager_repository.get_by_telegram_id(message.from_user.id)
    if manager is None:
        logger.error("Manager not found: telegram_id=%s", message.from_user.id)
        await message.answer(text=AddTemplates.error_try_later())
        await _clear_add_flow_key(redis, message.message_thread_id)
        await state.clear()
        return

    try:
        course = await add_service.create_link(
            manager_id=manager.id,
            name=data["name"],
            passport_file_id=data["passport_file_id"],
            receipt_file_id=data["receipt_file_id"],
            receipt_price=data["receipt_price"],
            card_file_id=data["card_file_id"],
            card_number=data["card_number"],
            card_holder_name=data["card_holder"],
            birth_date=data.get("birth_date"),
            existing_user_id=data.get("existing_user_id"),
        )
    except Exception:
        logger.exception("Failed to create link for manager=%s", manager.id)
        await message.answer(text=AddTemplates.error_try_later())
        return

    bot_info = await message.bot.me()
    bot_username = bot_info.username or ""

    # NEW message with link
    await message.answer(
        text=AddTemplates.link_created(
            data["name"], bot_username, course.invite_code or "",
        ),
    )

    # Notify accountants
    await _notify_accountants(message, data, course.id, manager_repository)

    await _clear_add_flow_key(redis, message.message_thread_id)
    await state.clear()


async def _notify_accountants(
    message: Message,
    data: dict,
    course_id: int,
    manager_repository: ManagerRepository,
) -> None:
    try:
        accountants = await manager_repository.get_active_by_role("accountant")
    except Exception:
        logger.exception("Failed to fetch accountants for course_id=%d", course_id)
        return

    if not accountants:
        return

    caption = AddTemplates.accountant_caption(
        name=data["name"],
        card_number=data["card_number"],
        card_holder_name=data["card_holder"],
    )
    media = [
        InputMediaPhoto(
            media=data["passport_file_id"], caption=caption, parse_mode="HTML",
        ),
        InputMediaPhoto(media=data["receipt_file_id"]),
        InputMediaPhoto(media=data["card_file_id"]),
    ]
    keyboard = payment_receipt_keyboard(course_id)

    for accountant in accountants:
        try:
            await message.bot.send_media_group(
                chat_id=accountant.telegram_id, media=media,
            )
            await message.bot.send_message(
                chat_id=accountant.telegram_id,
                text=AddTemplates.accountant_send_receipt(),
                reply_markup=keyboard,
            )
        except Exception:
            logger.warning(
                "Failed to notify accountant=%d for course_id=%d",
                accountant.telegram_id, course_id,
            )


@router.message(AddStates.waiting_card)
async def on_card_unsupported(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await delete_user_message(message)
    await edit_or_send(
        message, state, data.get("bot_message_id"),
        text=AddTemplates.photo_only(),
    )
