"""Сервис для работы с топиками в Telegram группе."""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.utils.logger import log_error
from app import templates


class TopicService:
    """Управляет топиками для девушек."""

    def __init__(self, bot: Bot, group_chat_id: int):
        self.bot = bot
        self.group_chat_id = group_chat_id

    async def create_topic(self, girl_name: str, manager_name: str, total_days: int = 21) -> int | None:
        topic_name = templates.TOPIC_NAME.format(
            girl_name=girl_name,
            manager_name=manager_name,
            completed_days=0,
            total_days=total_days,
        )

        try:
            result = await self.bot.create_forum_topic(
                chat_id=self.group_chat_id,
                name=topic_name,
            )

            # Удаляем служебное сообщение о создании
            try:
                await self.bot.delete_message(
                    chat_id=self.group_chat_id,
                    message_id=result.message_thread_id,
                )
            except Exception:
                pass

            return result.message_thread_id
        except TelegramAPIError as e:
            log_error(f"Failed to create topic: {e}")
            return None

    async def update_progress(
        self,
        topic_id: int,
        girl_name: str,
        manager_name: str,
        completed_days: int,
        total_days: int = 21,
    ) -> None:
        """Обновляет прогресс в названии топика."""
        topic_name = templates.TOPIC_NAME.format(
            girl_name=girl_name,
            manager_name=manager_name,
            completed_days=completed_days,
            total_days=total_days,
        )

        try:
            await self.bot.edit_forum_topic(
                chat_id=self.group_chat_id,
                message_thread_id=topic_id,
                name=topic_name,
            )
        except TelegramAPIError as e:
            log_error(f"Failed to update topic: {e}")

    async def send_registration_info(
        self,
        topic_id: int,
        course_id: int,
        cycle_day: int,
        intake_time: str,
        start_date: str,
    ) -> None:
        """Отправляет информацию о регистрации в топик."""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        text = templates.TOPIC_REGISTRATION.format(
            cycle_day=cycle_day,
            intake_time=intake_time,
            start_date=start_date,
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Продлить +21",
                    callback_data=f"extend_{course_id}",
                ),
                InlineKeyboardButton(
                    text="🏁 Завершить",
                    callback_data=f"complete_{course_id}",
                ),
            ]
        ])

        try:
            await self.bot.send_message(
                chat_id=self.group_chat_id,
                message_thread_id=topic_id,
                text=text,
                reply_markup=keyboard,
            )
        except TelegramAPIError as e:
            log_error(f"Failed to send registration info: {e}")

    async def send_video(self, topic_id: int, video_file_id: str, day: int, total_days: int = 21) -> None:
        """Отправляет видео-кружочек в топик."""
        try:
            await self.bot.send_video_note(
                chat_id=self.group_chat_id,
                message_thread_id=topic_id,
                video_note=video_file_id,
            )
            await self.bot.send_message(
                chat_id=self.group_chat_id,
                message_thread_id=topic_id,
                text=templates.TOPIC_DAY_COMPLETE.format(day=day, total_days=total_days),
            )
        except TelegramAPIError as e:
            log_error(f"Failed to send video: {e}")

    async def send_review_buttons(
            self,
            topic_id: int,
            course_id: int,
            day: int,
            reason: str,
            total_days: int = 21,
    ) -> None:
        """Отправляет кнопки для проверки видео менеджером."""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять",
                    callback_data=f"verify_ok_{course_id}_{day}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"verify_no_{course_id}_{day}",
                ),
            ]
        ])

        text = templates.TOPIC_REVIEW_REQUEST.format(day=day, reason=reason, total_days=total_days)

        try:
            await self.bot.send_message(
                chat_id=self.group_chat_id,
                message_thread_id=topic_id,
                text=text,
                reply_markup=keyboard,
            )
        except TelegramAPIError as e:
            log_error(f"Failed to send review buttons: {e}")

    async def close_topic(self, topic_id: int) -> None:
        """Закрывает топик (курс завершён или отказ)."""
        try:
            await self.bot.close_forum_topic(
                chat_id=self.group_chat_id,
                message_thread_id=topic_id,
            )
        except TelegramAPIError as e:
            log_error(f"Failed to close topic: {e}")