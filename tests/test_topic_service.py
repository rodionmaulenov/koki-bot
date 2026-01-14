"""Тесты для TopicService."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.exceptions import TelegramAPIError

from app.services.topic import TopicService
from app import templates


class TestTopicServiceCreateTopic:
    """Тесты создания топика."""

    @pytest.mark.asyncio
    async def test_creates_topic(self, bot):
        """Создаёт топик и возвращает ID."""
        mock_result = MagicMock()
        mock_result.message_thread_id = 12345
        bot.create_forum_topic = AsyncMock(return_value=mock_result)
        bot.delete_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        topic_id = await service.create_topic(
            girl_name="Иванова Мария Петровна",
            manager_name="Айнура",
        )

        assert topic_id == 12345
        bot.create_forum_topic.assert_called_once()

        # Проверяем формат названия
        call_args = bot.create_forum_topic.call_args
        name = call_args.kwargs["name"]
        assert "/" in name
        assert "Иванова М. П." in name
        assert "Айнура" in name
        assert "0/21" in name

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
        call_args = bot.create_forum_topic.call_args
        assert "0/42" in call_args.kwargs["name"]

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
        assert "/" in call_args.kwargs["name"]

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
    async def test_sends_registration_info_and_returns_message_id(self, bot):
        """Отправляет информацию о регистрации и возвращает message_id."""
        mock_message = MagicMock()
        mock_message.message_id = 999
        bot.send_message = AsyncMock(return_value=mock_message)

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        message_id = await service.send_registration_info(
            topic_id=12345,
            course_id=100,
            cycle_day=5,
            intake_time="14:30",
            start_date="8 Янв 26",
        )

        assert message_id == 999
        bot.send_message.assert_called_once()

        call_args = bot.send_message.call_args
        assert call_args.kwargs["message_thread_id"] == 12345
        assert "14:30" in call_args.kwargs["text"]
        assert "8 Янв 26" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_registration_buttons_use_templates(self, bot):
        """Кнопки используют шаблоны из templates."""
        mock_message = MagicMock()
        mock_message.message_id = 999
        bot.send_message = AsyncMock(return_value=mock_message)

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.send_registration_info(
            topic_id=12345,
            course_id=100,
            cycle_day=5,
            intake_time="14:30",
            start_date="8 Янв 26",
        )

        call_args = bot.send_message.call_args
        keyboard = call_args.kwargs["reply_markup"]
        buttons = keyboard.inline_keyboard[0]

        # Проверяем тексты кнопок из templates
        button_texts = [btn.text for btn in buttons]
        assert templates.BTN_EXTEND in button_texts
        assert templates.BTN_COMPLETE in button_texts

        # Проверяем callback_data
        assert any("extend_100" in btn.callback_data for btn in buttons)
        assert any("complete_100" in btn.callback_data for btn in buttons)

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, bot):
        """Возвращает None при ошибке API."""
        bot.send_message = AsyncMock(
            side_effect=TelegramAPIError(method="sendMessage", message="Error")
        )

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        message_id = await service.send_registration_info(
            topic_id=12345,
            course_id=100,
            cycle_day=5,
            intake_time="14:30",
            start_date="8 Янв 26",
        )

        assert message_id is None


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

        # Проверяем video_note
        video_call = bot.send_video_note.call_args
        assert video_call.kwargs["video_note"] == "video_abc123"
        assert video_call.kwargs["message_thread_id"] == 12345

        # Проверяем текст сообщения
        msg_call = bot.send_message.call_args
        text = msg_call.kwargs["text"]
        assert "7" in text
        assert "21" in text


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

    @pytest.mark.asyncio
    async def test_review_buttons_use_templates(self, bot):
        """Кнопки проверки используют шаблоны."""
        bot.send_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.send_review_buttons(
            topic_id=12345,
            course_id=100,
            day=5,
            reason="Тест",
            total_days=21,
        )

        call_args = bot.send_message.call_args
        keyboard = call_args.kwargs["reply_markup"]
        buttons = keyboard.inline_keyboard[0]

        button_texts = [btn.text for btn in buttons]
        assert templates.BTN_VERIFY_OK in button_texts
        assert templates.BTN_VERIFY_NO in button_texts

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


class TestTopicServiceRenameOnClose:
    """Тесты переименования топика при закрытии."""

    @pytest.mark.asyncio
    async def test_renames_topic_completed(self, bot):
        """Переименовывает топик при completed."""
        bot.edit_forum_topic = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.rename_topic_on_close(
            topic_id=12345,
            girl_name="Иванова Мария Петровна",
            manager_name="Айнура",
            completed_days=21,
            total_days=21,
            status="completed",
        )

        bot.edit_forum_topic.assert_called_once()
        call_args = bot.edit_forum_topic.call_args
        name = call_args.kwargs["name"]

        assert "/" in name
        assert "Иванова М. П." in name
        assert "Айнура" in name
        assert "21/21" in name

    @pytest.mark.asyncio
    async def test_renames_topic_refused(self, bot):
        """Переименовывает топик при refused."""
        bot.edit_forum_topic = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.rename_topic_on_close(
            topic_id=12345,
            girl_name="Петрова Анна Сергеевна",
            manager_name="Акмарал",
            completed_days=5,
            total_days=21,
            status="refused",
        )

        call_args = bot.edit_forum_topic.call_args
        name = call_args.kwargs["name"]

        assert "/" in name
        assert "Петрова А. С." in name
        assert "5/21" in name

    @pytest.mark.asyncio
    async def test_uses_templates(self, bot):
        """Использует шаблоны из templates."""
        bot.edit_forum_topic = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.rename_topic_on_close(
            topic_id=12345,
            girl_name="Тест",
            manager_name="Тест",
            completed_days=10,
            total_days=21,
            status="completed",
        )

        call_args = bot.edit_forum_topic.call_args
        name = call_args.kwargs["name"]

        # Проверяем что формат соответствует шаблону
        expected = templates.TOPIC_NAME_COMPLETED.format(
            girl_name="Тест",
            manager_name="Тест",
            completed_days=10,
            total_days=21,
        )
        assert name == expected

    @pytest.mark.asyncio
    async def test_handles_api_error(self, bot):
        """Обрабатывает ошибку API без исключения."""
        bot.edit_forum_topic = AsyncMock(
            side_effect=TelegramAPIError(method="editForumTopic", message="Error")
        )

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        # Не должно бросить исключение
        await service.rename_topic_on_close(
            topic_id=12345,
            girl_name="Тест",
            manager_name="Тест",
            completed_days=5,
            total_days=21,
            status="refused",
        )


class TestTopicServiceSendClosureMessage:
    """Тесты отправки сообщения о закрытии."""

    @pytest.mark.asyncio
    async def test_sends_completed_message(self, bot):
        """Отправляет сообщение о завершении курса."""
        bot.send_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.send_closure_message(
            topic_id=12345,
            status="completed",
            reason="",
        )

        bot.send_message.assert_called_once()
        call_args = bot.send_message.call_args
        text = call_args.kwargs["text"]

        assert "✅" in text
        assert "Программа завершена" in text
        assert "Курс пройден полностью" in text
        assert call_args.kwargs["message_thread_id"] == 12345

    @pytest.mark.asyncio
    async def test_sends_refused_message_with_reason(self, bot):
        """Отправляет сообщение об отказе с причиной."""
        bot.send_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.send_closure_message(
            topic_id=12345,
            status="refused",
            reason="пропуск более 2 часов",
        )

        call_args = bot.send_message.call_args
        text = call_args.kwargs["text"]

        assert "❌" in text
        assert "Программа завершена" in text
        assert "пропуск более 2 часов" in text

    @pytest.mark.asyncio
    async def test_includes_formatted_date(self, bot):
        """Включает отформатированную дату."""
        bot.send_message = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.send_closure_message(
            topic_id=12345,
            status="completed",
            reason="",
        )

        call_args = bot.send_message.call_args
        text = call_args.kwargs["text"]

        # Дата в формате "10 Янв 26"
        assert "📅" in text

    @pytest.mark.asyncio
    async def test_handles_api_error(self, bot):
        """Обрабатывает ошибку API без исключения."""
        bot.send_message = AsyncMock(
            side_effect=TelegramAPIError(method="sendMessage", message="Error")
        )

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        # Не должно бросить исключение
        await service.send_closure_message(
            topic_id=12345,
            status="refused",
            reason="тест",
        )


class TestTopicServiceRemoveRegistrationButtons:
    """Тесты удаления кнопок из сообщения регистрации."""

    @pytest.mark.asyncio
    async def test_removes_buttons(self, bot):
        """Убирает кнопки из сообщения."""
        bot.edit_message_text = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.remove_registration_buttons(
            message_id=999,
            cycle_day=4,
            intake_time="14:30",
            start_date="10 Янв 26",
        )

        bot.edit_message_text.assert_called_once()
        call_args = bot.edit_message_text.call_args

        assert call_args.kwargs["message_id"] == 999
        assert call_args.kwargs["chat_id"] == -1001234567890
        assert call_args.kwargs["reply_markup"] is None  # Кнопки убраны

        # Текст сохраняется
        text = call_args.kwargs["text"]
        assert "14:30" in text
        assert "10 Янв 26" in text

    @pytest.mark.asyncio
    async def test_preserves_original_text(self, bot):
        """Сохраняет оригинальный текст сообщения."""
        bot.edit_message_text = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        await service.remove_registration_buttons(
            message_id=999,
            cycle_day=3,
            intake_time="09:00",
            start_date="15 Фев 26",
        )

        call_args = bot.edit_message_text.call_args
        text = call_args.kwargs["text"]

        # Проверяем что текст соответствует шаблону
        expected = templates.TOPIC_REGISTRATION.format(
            cycle_day=3,
            intake_time="09:00",
            start_date="15 Фев 26",
        )
        assert text == expected

    @pytest.mark.asyncio
    async def test_handles_api_error(self, bot):
        """Обрабатывает ошибку API без исключения."""
        bot.edit_message_text = AsyncMock(
            side_effect=TelegramAPIError(method="editMessageText", message="Error")
        )

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        # Не должно бросить исключение
        await service.remove_registration_buttons(
            message_id=999,
            cycle_day=4,
            intake_time="14:30",
            start_date="10 Янв 26",
        )


class TestTopicClosureFullSequence:
    """Интеграционные тесты полной последовательности закрытия."""

    @pytest.mark.asyncio
    async def test_full_closure_sequence_completed(self, bot):
        """Полная последовательность закрытия при completed."""
        bot.edit_forum_topic = AsyncMock()
        bot.edit_message_text = AsyncMock()
        bot.send_message = AsyncMock()
        bot.close_forum_topic = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        # 1. Переименовать
        await service.rename_topic_on_close(
            topic_id=12345,
            girl_name="Иванова Мария",
            manager_name="Айнура",
            completed_days=21,
            total_days=21,
            status="completed",
        )

        # 2. Убрать кнопки
        await service.remove_registration_buttons(
            message_id=999,
            cycle_day=4,
            intake_time="14:30",
            start_date="10 Янв 26",
        )

        # 3. Сообщение о закрытии
        await service.send_closure_message(
            topic_id=12345,
            status="completed",
            reason="",
        )

        # 4. Закрыть
        await service.close_topic(topic_id=12345)

        # Проверяем все вызовы
        bot.edit_forum_topic.assert_called_once()
        bot.edit_message_text.assert_called_once()
        bot.send_message.assert_called_once()
        bot.close_forum_topic.assert_called_once()

        # Проверяем порядок и содержимое
        rename_name = bot.edit_forum_topic.call_args.kwargs["name"]
        assert "/" in rename_name

        closure_text = bot.send_message.call_args.kwargs["text"]
        assert "Курс пройден полностью" in closure_text

    @pytest.mark.asyncio
    async def test_full_closure_sequence_refused(self, bot):
        """Полная последовательность закрытия при refused."""
        bot.edit_forum_topic = AsyncMock()
        bot.edit_message_text = AsyncMock()
        bot.send_message = AsyncMock()
        bot.close_forum_topic = AsyncMock()

        service = TopicService(bot=bot, group_chat_id=-1001234567890)

        # Полная последовательность
        await service.rename_topic_on_close(
            topic_id=12345,
            girl_name="Петрова Анна",
            manager_name="Акмарал",
            completed_days=5,
            total_days=21,
            status="refused",
        )

        await service.remove_registration_buttons(
            message_id=999,
            cycle_day=4,
            intake_time="10:00",
            start_date="5 Янв 26",
        )

        await service.send_closure_message(
            topic_id=12345,
            status="refused",
            reason=templates.REFUSAL_REASON_MISSED,
        )

        await service.close_topic(topic_id=12345)

        # Проверяем
        rename_name = bot.edit_forum_topic.call_args.kwargs["name"]
        assert "/" in rename_name
        assert "5/21" in rename_name

        closure_text = bot.send_message.call_args.kwargs["text"]
        assert templates.REFUSAL_REASON_MISSED in closure_text