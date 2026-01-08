"""Обработка всех остальных сообщений."""

from aiogram import Router, F
from aiogram.types import Message

from app import templates

router = Router()

router.message.filter(F.chat.type == "private")


@router.message()
async def fallback_handler(message: Message):
    """Любое сообщение которое не обработали другие handlers."""
    await message.answer(templates.FALLBACK_MESSAGE)