"""Сервис для работы с топиками в Telegram группе."""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.utils.logger import log_error
from app.utils.time_utils import get_tashkent_now, format_date
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
    ) -> int | None:
        """Отправляет информацию о регистрации в топик. Возвращает message_id."""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        text = templates.TOPIC_REGISTRATION.format(
            cycle_day=cycle_day,
            intake_time=intake_time,
            start_date=start_date,
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=templates.BTN_EXTEND,
                    callback_data=f"extend_{course_id}",
                ),
                InlineKeyboardButton(
                    text=templates.BTN_COMPLETE,
                    callback_data=f"complete_{course_id}",
                ),
            ]
        ])

        try:
            message = await self.bot.send_message(
                chat_id=self.group_chat_id,
                message_thread_id=topic_id,
                text=text,
                reply_markup=keyboard,
            )
            return message.message_id
        except TelegramAPIError as e:
            log_error(f"Failed to send registration info: {e}")
            return None

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
                    text=templates.BTN_VERIFY_OK,
                    callback_data=f"verify_ok_{course_id}_{day}",
                ),
                InlineKeyboardButton(
                    text=templates.BTN_VERIFY_NO,
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

    async def rename_topic_on_close(
            self,
            topic_id: int,
            girl_name: str,
            manager_name: str,
            completed_days: int,
            total_days: int,
            status: str,
    ) -> None:
        """Переименовывает топик при закрытии (✅ или ❌)."""
        if status == "completed":
            topic_name = templates.TOPIC_NAME_COMPLETED.format(
                girl_name=girl_name,
                manager_name=manager_name,
                completed_days=completed_days,
                total_days=total_days,
            )
        else:
            topic_name = templates.TOPIC_NAME_REFUSED.format(
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
            log_error(f"Failed to rename topic on close: {e}")

    async def send_closure_message(
            self,
            topic_id: int,
            status: str,
            reason: str = "",
    ) -> None:
        """Отправляет сообщение о закрытии в топик."""
        today = get_tashkent_now().date().isoformat()
        date_str = format_date(today)

        if status == "completed":
            text = templates.TOPIC_CLOSURE_COMPLETED.format(date=date_str)
        else:
            text = templates.TOPIC_CLOSURE_REFUSED.format(date=date_str, reason=reason)

        try:
            await self.bot.send_message(
                chat_id=self.group_chat_id,
                message_thread_id=topic_id,
                text=text,
            )
        except TelegramAPIError as e:
            log_error(f"Failed to send closure message: {e}")

    async def remove_registration_buttons(
            self,
            message_id: int,
            cycle_day: int,
            intake_time: str,
            start_date: str,
    ) -> None:
        """Убирает кнопки из сообщения регистрации."""
        text = templates.TOPIC_REGISTRATION.format(
            cycle_day=cycle_day,
            intake_time=intake_time,
            start_date=start_date,
        )

        try:
            await self.bot.edit_message_text(
                chat_id=self.group_chat_id,
                message_id=message_id,
                text=text,
                reply_markup=None,
            )
        except TelegramAPIError as e:
            log_error(f"Failed to remove registration buttons: {e}")