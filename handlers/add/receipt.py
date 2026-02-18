import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from dishka.integrations.aiogram import FromDishka

from models.ocr import OCRServerError
from services.ocr_service import OCRService
from states.add import AddStates
from templates import AddTemplates
from utils.message import delete_user_message, edit_or_send, extract_image_file_id
from utils.validators import validate_receipt_price

logger = logging.getLogger(__name__)

router = Router()


@router.message(AddStates.waiting_receipt, F.photo)
async def on_receipt_photo(
    message: Message,
    state: FSMContext,
    ocr_service: FromDishka[OCRService],
) -> None:
    await _handle_receipt_file(message, state, message.photo[-1].file_id, ocr_service)


@router.message(AddStates.waiting_receipt, F.document)
async def on_receipt_document(
    message: Message,
    state: FSMContext,
    ocr_service: FromDishka[OCRService],
) -> None:
    file_id = await extract_image_file_id(
        message, state, AddTemplates.photo_only(),
    )
    if file_id is None:
        return
    await _handle_receipt_file(message, state, file_id, ocr_service)


async def _handle_receipt_file(
    message: Message,
    state: FSMContext,
    file_id: str,
    ocr_service: OCRService,
) -> None:
    data = await state.get_data()
    bot_message_id = data.get("bot_message_id")

    await delete_user_message(message)
    await state.update_data(receipt_file_id=file_id)

    await edit_or_send(
        message, state, bot_message_id,
        text=AddTemplates.ask_receipt_processing(),
    )

    # Re-read bot_message_id in case edit_or_send created a new message
    data = await state.get_data()
    bot_message_id = data.get("bot_message_id")

    try:
        result = await ocr_service.process_receipt(file_id)
    except OCRServerError:
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.ocr_server_error(),
        )
        return

    if not result.is_document:
        logger.info("Not a receipt, file_id=%s", file_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.not_a_receipt(),
        )
        return

    if not result.has_kok:
        logger.info("Receipt OCR: no KOK found, file_id=%s", file_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.ocr_receipt_no_kok(),
        )
        return

    if result.price is None:
        logger.info("Receipt OCR: KOK found but no price, file_id=%s", file_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.ocr_receipt_no_price(),
        )
        return

    price = validate_receipt_price(str(result.price))
    if not price:
        logger.info("Receipt OCR: price %s out of range, file_id=%s", result.price, file_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=AddTemplates.ocr_receipt_no_price(),
        )
        return

    # Success
    await edit_or_send(
        message, state, bot_message_id,
        text=AddTemplates.ocr_receipt_result(price),
    )
    await state.update_data(receipt_price=price)
    logger.info("Receipt OCR success: has_kok=True, price=%d", price)

    # Success → NEW message for card step
    sent = await message.answer(text=AddTemplates.ask_card())
    await state.update_data(bot_message_id=sent.message_id)
    await state.set_state(AddStates.waiting_card)


@router.message(AddStates.waiting_receipt)
async def on_receipt_unsupported(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await delete_user_message(message)
    await edit_or_send(
        message, state, data.get("bot_message_id"),
        text=AddTemplates.photo_only(),
    )