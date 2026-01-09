"""Тесты для TopicService."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.exceptions import TelegramAPIError

from app.services.topic import TopicService


class TestTopicServiceCreateTopic:
    """Тесты создания топика."""

    @pytest.mark.asyncio
    async def test_creates_topic(self, bot):
        """Создаёт топик и возвращает ID."""
        # Настраиваем мок
        mock_result = MagicMock()
        mock_result.message_thread_id = 12345
        bot.create_forum_topic = AsyncMock(return_value=mock_result)
        bot.delete_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        topic_id = await service.create_topic(
            girl_name="Иванова Мария",
            manager_name="Айнура",
        )

        assert topic_id == 12345
        bot.create_forum_topic.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_topic_with_custom_days(self, bot):
        """Создаёт топик с кастомным количеством дней."""
        mock_result = MagicMock()
        mock_result.message_thread_id = 67890
        bot.create_forum_topic = AsyncMock(return_value=mock_result)
        bot.delete_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        topic_id = await service.create_topic(
            girl_name="Петрова Анна",
            manager_name="Акмарал",
            total_days=42,
        )

        assert topic_id == 67890
        # Проверяем что в названии есть /42
        call_args = bot.create_forum_topic.call_args
        assert "/42" in call_args.kwargs["name"]

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, bot):
        """Возвращает None при ошибке API."""
        bot.create_forum_topic = AsyncMock(
            side_effect=TelegramAPIError(method="createForumTopic", message="Error")
        )

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        topic_id = await service.create_topic(
            girl_name="Ошибка",
            manager_name="Тест",
        )

        assert topic_id is None


class TestTopicServiceUpdateProgress:
    """Тесты обновления прогресса."""

    @pytest.mark.asyncio
    async def test_updates_progress(self, bot):
        """Обновляет прогресс в названии топика."""
        bot.edit_forum_topic = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.update_progress(
            topic_id=12345,
            girl_name="Иванова Мария",
            manager_name="Айнура",
            completed_days=5,
            total_days=21,
        )

        bot.edit_forum_topic.assert_called_once()
        call_args = bot.edit_forum_topic.call_args
        assert "5/21" in call_args.kwargs["name"]

    @pytest.mark.asyncio
    async def test_updates_extended_course(self, bot):
        """Обновляет прогресс продлённого курса."""
        bot.edit_forum_topic = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.update_progress(
            topic_id=12345,
            girl_name="Сидорова Елена",
            manager_name="Aidyn",
            completed_days=25,
            total_days=42,
        )

        call_args = bot.edit_forum_topic.call_args
        assert "25/42" in call_args.kwargs["name"]

    @pytest.mark.asyncio
    async def test_handles_api_error(self, bot):
        """Обрабатывает ошибку API без исключения."""
        bot.edit_forum_topic = AsyncMock(
            side_effect=TelegramAPIError(method="editForumTopic", message="Error")
        )

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        # Не должно бросить исключение
        await service.update_progress(
            topic_id=12345,
            girl_name="Тест",
            manager_name="Тест",
            completed_days=1,
        )


class TestTopicServiceSendRegistrationInfo:
    """Тесты отправки информации о регистрации."""

    @pytest.mark.asyncio
    async def test_sends_registration_info(self, bot):
        """Отправляет информацию о регистрации."""
        bot.send_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.send_registration_info(
            topic_id=12345,
            course_id=100,
            cycle_day=5,
            intake_time="14:30",
            start_date="2026-01-08",
        )

        bot.send_message.assert_called_once()
        call_args = bot.send_message.call_args

        # Проверяем параметры
        assert call_args.kwargs["message_thread_id"] == 12345
        assert "14:30" in call_args.kwargs["text"]

        # Проверяем кнопки
        keyboard = call_args.kwargs["reply_markup"]
        buttons = keyboard.inline_keyboard[0]
        assert any("extend_100" in btn.callback_data for btn in buttons)
        assert any("complete_100" in btn.callback_data for btn in buttons)


class TestTopicServiceSendVideo:
    """Тесты отправки видео."""

    @pytest.mark.asyncio
    async def test_sends_video_to_topic(self, bot):
        """Отправляет видео в топик."""
        bot.send_video_note = AsyncMock()
        bot.send_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.send_video(
            topic_id=12345,
            video_file_id="video_abc123",
            day=7,
            total_days=21,
        )

        bot.send_video_note.assert_called_once()
        bot.send_message.assert_called_once()

        # Проверяем текст сообщения
        call_args = bot.send_message.call_args
        text = call_args.kwargs["text"]
        assert "7" in text
        assert "21" in text

    @pytest.mark.asyncio
    async def test_sends_video_extended_course(self, bot):
        """Отправляет видео для продлённого курса."""
        bot.send_video_note = AsyncMock()
        bot.send_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.send_video(
            topic_id=12345,
            video_file_id="video_xyz789",
            day=25,
            total_days=42,
        )

        call_args = bot.send_message.call_args
        text = call_args.kwargs["text"]
        assert "25" in text
        assert "42" in text


class TestTopicServiceSendReviewButtons:
    """Тесты отправки кнопок проверки."""

    @pytest.mark.asyncio
    async def test_sends_review_buttons(self, bot):
        """Отправляет кнопки для проверки видео."""
        bot.send_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.send_review_buttons(
            topic_id=12345,
            course_id=100,
            day=5,
            reason="Не видно таблетку",
            total_days=21,
        )

        bot.send_message.assert_called_once()
        call_args = bot.send_message.call_args

        # Проверяем текст
        text = call_args.kwargs["text"]
        assert "Не видно таблетку" in text
        assert "5" in text

        # Проверяем кнопки
        keyboard = call_args.kwargs["reply_markup"]
        buttons = keyboard.inline_keyboard[0]
        assert any("verify_ok_100_5" in btn.callback_data for btn in buttons)
        assert any("verify_no_100_5" in btn.callback_data for btn in buttons)

    @pytest.mark.asyncio
    async def test_handles_api_error(self, bot):
        """Обрабатывает ошибку API без исключения."""
        bot.send_message = AsyncMock(
            side_effect=TelegramAPIError(method="sendMessage", message="Error")
        )

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        # Не должно бросить исключение
        await service.send_review_buttons(
            topic_id=12345,
            course_id=100,
            day=5,
            reason="Тест",
        )


class TestTopicServiceCloseTopic:
    """Тесты закрытия топика."""

    @pytest.mark.asyncio
    async def test_closes_topic(self, bot):
        """Закрывает топик."""
        bot.close_forum_topic = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.close_topic(topic_id=12345)

        bot.close_forum_topic.assert_called_once_with(
            chat_id=-1001234567890,
            message_thread_id=12345,
        )

    @pytest.mark.asyncio
    async def test_handles_api_error(self, bot):
        """Обрабатывает ошибку API без исключения."""
        bot.close_forum_topic = AsyncMock(
            side_effect=TelegramAPIError(method="closeForumTopic", message="Error")
        )

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        # Не должно бросить исключение
        await service.close_topic(topic_id=12345)