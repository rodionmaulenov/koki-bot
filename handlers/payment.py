import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka

from callbacks.payment import PaymentCallback
from keyboards.payment import payment_cancel_keyboard, payment_receipt_keyboard
from models.enums import CourseStatus
from models.ocr import OCRServerError
from repositories.course_repository import CourseRepository
from repositories.manager_repository import ManagerRepository
from repositories.payment_receipt_repository import PaymentReceiptRepository
from repositories.user_repository import UserRepository
from services.ocr_service import OCRService
from states.payment import PaymentStates
from templates import PaymentTemplates
from utils.message import delete_user_message, edit_or_send, extract_image_file_id

_PAYABLE_STATUSES = {CourseStatus.SETUP, CourseStatus.ACTIVE}

logger = logging.getLogger(__name__)

router = Router()


# ── Callback: send / cancel ─────────────────────────────────────────────────


@router.callback_query(PaymentCallback.filter(F.action == "send"))
async def on_send_receipt(
    callback: CallbackQuery,
    callback_data: PaymentCallback,
    state: FSMContext,
    course_repository: FromDishka[CourseRepository],
    user_repository: FromDishka[UserRepository],
) -> None:
    course_id = callback_data.course_id

    course = await course_repository.get_by_id(course_id)
    if course is None:
        await callback.answer("Курс не найден", show_alert=True)
        return

    if course.status not in _PAYABLE_STATUSES:
        await callback.answer(PaymentTemplates.course_not_payable(), show_alert=True)
        return

    user = await user_repository.get_by_id(course.user_id)
    if user is None:
        logger.error("User not found: user_id=%d for course_id=%d", course.user_id, course_id)
        await callback.answer("Ошибка", show_alert=True)
        return

    await callback.message.edit_reply_markup(
        reply_markup=payment_cancel_keyboard(course_id),
    )

    sent = await callback.message.answer(
        text=PaymentTemplates.ask_receipt(user.name),
    )

    await state.update_data(
        bot_message_id=sent.message_id,
        course_id=course_id,
        button_message_id=callback.message.message_id,
        manager_id=user.manager_id,
        girl_name=user.name,
    )
    await state.set_state(PaymentStates.waiting_receipt)
    await callback.answer()


@router.callback_query(PaymentCallback.filter(F.action == "cancel"))
async def on_cancel_receipt(
    callback: CallbackQuery,
    callback_data: PaymentCallback,
    state: FSMContext,
) -> None:
    data = await state.get_data()

    await callback.message.edit_reply_markup(
        reply_markup=payment_receipt_keyboard(callback_data.course_id),
    )

    bot_message_id = data.get("bot_message_id")
    if bot_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=bot_message_id,
            )
        except TelegramBadRequest:
            pass

    await state.clear()
    await callback.answer()


# ── Photo / document handlers ───────────────────────────────────────────────


@router.message(PaymentStates.waiting_receipt, F.photo)
async def on_receipt_photo(
    message: Message,
    state: FSMContext,
    ocr_service: FromDishka[OCRService],
    manager_repository: FromDishka[ManagerRepository],
    payment_receipt_repository: FromDishka[PaymentReceiptRepository],
) -> None:
    await _handle_receipt_file(
        message, state, message.photo[-1].file_id,
        ocr_service, manager_repository, payment_receipt_repository,
    )


@router.message(PaymentStates.waiting_receipt, F.document)
async def on_receipt_document(
    message: Message,
    state: FSMContext,
    ocr_service: FromDishka[OCRService],
    manager_repository: FromDishka[ManagerRepository],
    payment_receipt_repository: FromDishka[PaymentReceiptRepository],
) -> None:
    file_id = await extract_image_file_id(
        message, state, PaymentTemplates.photo_only(),
    )
    if file_id is None:
        return
    await _handle_receipt_file(
        message, state, file_id,
        ocr_service, manager_repository, payment_receipt_repository,
    )


async def _handle_receipt_file(
    message: Message,
    state: FSMContext,
    file_id: str,
    ocr_service: OCRService,
    manager_repository: ManagerRepository,
    payment_receipt_repository: PaymentReceiptRepository,
) -> None:
    data = await state.get_data()
    course_id = data.get("course_id")
    bot_message_id = data.get("bot_message_id")

    await delete_user_message(message)

    await edit_or_send(
        message, state, bot_message_id,
        text=PaymentTemplates.processing(),
    )

    data = await state.get_data()
    bot_message_id = data.get("bot_message_id")

    try:
        result = await ocr_service.process_payment_receipt(file_id)
    except OCRServerError:
        await edit_or_send(
            message, state, bot_message_id,
            text=PaymentTemplates.server_error(),
        )
        return

    if not result or not result.is_document:
        logger.info("Not a payment receipt, file_id=%s", file_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=PaymentTemplates.not_a_receipt(),
        )
        return

    if result.amount is None:
        logger.info("Payment receipt OCR: no amount, file_id=%s", file_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=PaymentTemplates.no_amount(),
        )
        return

    accountant = await manager_repository.get_by_telegram_id(message.from_user.id)
    if accountant is None:
        logger.error("Accountant not found: telegram_id=%d", message.from_user.id)
        await edit_or_send(
            message, state, bot_message_id,
            text=PaymentTemplates.server_error(),
        )
        return

    existing = await payment_receipt_repository.get_by_course_id(course_id)
    if existing is not None:
        logger.info("Duplicate receipt upload attempt: course_id=%d", course_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=PaymentTemplates.already_uploaded(),
        )
        await state.clear()
        return

    try:
        await payment_receipt_repository.create(
            course_id=course_id,
            accountant_id=accountant.id,
            receipt_file_id=file_id,
            amount=result.amount,
        )
    except Exception:
        logger.exception("Failed to save payment receipt for course_id=%d", course_id)
        await edit_or_send(
            message, state, bot_message_id,
            text=PaymentTemplates.server_error(),
        )
        return

    logger.info(
        "Payment receipt saved: course_id=%d, amount=%d, accountant=%d",
        course_id, result.amount, accountant.id,
    )

    await edit_or_send(
        message, state, bot_message_id,
        text=PaymentTemplates.receipt_accepted(result.amount),
    )

    # Mark button message as done
    button_message_id = data.get("button_message_id")
    if button_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=button_message_id,
                text=PaymentTemplates.receipt_uploaded(),
            )
        except TelegramBadRequest:
            pass

    # Forward receipt to girl's manager
    girl_name = data.get("girl_name", "")
    manager_id = data.get("manager_id")
    await _forward_to_manager(
        message, file_id, course_id, result.amount,
        girl_name, manager_id, manager_repository,
    )

    await state.clear()


# ── Unsupported message ─────────────────────────────────────────────────────


@router.message(PaymentStates.waiting_receipt)
async def on_receipt_unsupported(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await delete_user_message(message)
    await edit_or_send(
        message, state, data.get("bot_message_id"),
        text=PaymentTemplates.photo_only(),
    )


# ── Forward to manager ──────────────────────────────────────────────────────


async def _forward_to_manager(
    message: Message,
    file_id: str,
    course_id: int,
    amount: int,
    girl_name: str,
    manager_id: int | None,
    manager_repository: ManagerRepository,
) -> None:
    if manager_id is None:
        return

    try:
        manager = await manager_repository.get_by_id(manager_id)
        if manager is None:
            logger.warning(
                "Manager not found: id=%d for course_id=%d", manager_id, course_id,
            )
            return

        await message.bot.send_photo(
            chat_id=manager.telegram_id,
            photo=file_id,
            caption=PaymentTemplates.manager_receipt(girl_name, amount),
        )
    except Exception:
        logger.warning(
            "Failed to forward receipt to manager=%d for course_id=%d",
            manager_id, course_id, exc_info=True,
        )
