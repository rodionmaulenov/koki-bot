import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from dishka.integrations.aiogram import FromDishka

from callbacks.menu import MenuAction, MenuCallback
from callbacks.reissue import ReissueCallback
from keyboards.reissue import reissue_list_keyboard
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.add_service import AddService
from templates import AddTemplates, ReissueTemplates
from utils.message import edit_or_send_callback
from utils.time import get_tashkent_now

logger = logging.getLogger(__name__)

router = Router()

EVENING_CUTOFF_HOUR = 20


@router.callback_query(MenuCallback.filter(F.action == MenuAction.REISSUE))
async def on_reissue_start(
    callback: CallbackQuery,
    add_service: FromDishka[AddService],
    manager_repository: FromDishka[ManagerRepository],
) -> None:
    manager = await manager_repository.get_by_telegram_id(callback.from_user.id)
    if manager is None:
        logger.warning("Reissue denied, not a manager: telegram_id=%s", callback.from_user.id)
        await callback.answer(ReissueTemplates.manager_only(), show_alert=True)
        return

    now = get_tashkent_now()
    if now.hour >= EVENING_CUTOFF_HOUR:
        await callback.answer(AddTemplates.time_restricted(), show_alert=True)
        return

    try:
        girls = await add_service.get_reissuable_girls(manager.id)
    except Exception:
        logger.exception("Failed to get reissuable girls: manager_id=%s", manager.id)
        await callback.answer(ReissueTemplates.error_try_later(), show_alert=True)
        return

    if not girls:
        await callback.answer(ReissueTemplates.no_girls(), show_alert=True)
        return

    await callback.answer()

    await callback.message.answer(
        text=ReissueTemplates.select_girl(girls),
        reply_markup=reissue_list_keyboard(girls),
    )


@router.callback_query(ReissueCallback.filter())
async def on_girl_selected(
    callback: CallbackQuery,
    callback_data: ReissueCallback,
    state: FSMContext,
    add_service: FromDishka[AddService],
    user_repository: FromDishka[UserRepository],
) -> None:
    await callback.answer()

    try:
        course = await add_service.reissue_link(callback_data.course_id)
    except Exception:
        logger.exception(
            "Failed to reissue link for course_id=%s", callback_data.course_id,
        )
        await edit_or_send_callback(
            callback, state,
            text=ReissueTemplates.error_try_later(),
        )
        return

    user = await user_repository.get_by_id(course.user_id)
    name = user.name if user else ""

    bot_info = await callback.bot.me()
    bot_username = bot_info.username or ""

    await edit_or_send_callback(
        callback, state,
        text=ReissueTemplates.link_reissued(name, bot_username, course.invite_code or ""),
    )
