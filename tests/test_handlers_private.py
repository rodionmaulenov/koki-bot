"""Тесты для handlers/private.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta

from app import templates
from app.utils.time_utils import get_tashkent_now


class TestUnderstandCallback:
    """Тесты для understand_callback."""

    @pytest.mark.asyncio
    async def test_expired_course_created_yesterday(
        self,
        mock_callback,
        mock_user_service,
        mock_course_service,
    ):
        """Курс создан вчера — показать expired."""
        from app.handlers.private import understand_callback

        yesterday = (get_tashkent_now() - timedelta(days=1)).isoformat()

        mock_user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})
        mock_course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "created_at": yesterday,
            "status": "setup",
        })
        mock_course_service.set_expired = AsyncMock()

        callback = mock_callback(data="understand")

        await understand_callback(
            callback=callback,
            user_service=mock_user_service,
            course_service=mock_course_service,
        )

        mock_course_service.set_expired.assert_called_once_with(1)
        callback.message.edit_text.assert_called_once_with(
            templates.TOO_LATE_REGISTRATION_EXPIRED
        )

    @pytest.mark.asyncio
    async def test_course_created_today_proceeds(
        self,
        mock_callback,
        mock_user_service,
        mock_course_service,
    ):
        """Курс создан сегодня — продолжить регистрацию."""
        from app.handlers.private import understand_callback

        today = get_tashkent_now().isoformat()

        mock_user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})
        mock_course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "created_at": today,
            "status": "setup",
        })
        mock_course_service.set_expired = AsyncMock()

        callback = mock_callback(data="understand")

        await understand_callback(
            callback=callback,
            user_service=mock_user_service,
            course_service=mock_course_service,
        )

        callback.message.delete.assert_called_once()
        callback.message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_user_error(
        self,
        mock_callback,
        mock_user_service,
        mock_course_service,
    ):
        """Пользователь не найден."""
        from app.handlers.private import understand_callback

        mock_user_service.get_by_telegram_id = AsyncMock(return_value=None)

        callback = mock_callback(data="understand")

        await understand_callback(
            callback=callback,
            user_service=mock_user_service,
            course_service=mock_course_service,
        )

        callback.message.edit_text.assert_called_once_with(templates.ERROR_NO_USER)


class TestCycleDayCallback:
    """Тесты для cycle_day_callback."""

    @pytest.mark.asyncio
    async def test_expired_course_created_yesterday(
        self,
        mock_callback,
        mock_user_service,
        mock_course_service,
    ):
        """Курс создан вчера — показать expired."""
        from app.handlers.private import cycle_day_callback

        yesterday = (get_tashkent_now() - timedelta(days=1)).isoformat()

        mock_user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})
        mock_course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "created_at": yesterday,
            "status": "setup",
        })
        mock_course_service.set_expired = AsyncMock()

        callback = mock_callback(data="cycle_4")

        await cycle_day_callback(
            callback=callback,
            course_service=mock_course_service,
            user_service=mock_user_service,
        )

        mock_course_service.set_expired.assert_called_once_with(1)
        callback.message.edit_text.assert_called_once_with(
            templates.TOO_LATE_REGISTRATION_EXPIRED
        )

    @pytest.mark.asyncio
    async def test_day4_too_late_no_time_slots(
        self,
        mock_callback,
        mock_user_service,
        mock_course_service,
    ):
        """День 4, нет доступных слотов времени."""
        from app.handlers.private import cycle_day_callback

        today = get_tashkent_now().isoformat()

        mock_user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})
        mock_course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "created_at": today,
            "status": "setup",
        })
        mock_course_service.set_expired = AsyncMock()

        callback = mock_callback(data="cycle_4")

        # Мокаем time_keyboard_today чтобы вернул None
        with patch("app.handlers.private.time_keyboard_today", return_value=None):
            await cycle_day_callback(
                callback=callback,
                course_service=mock_course_service,
                user_service=mock_user_service,
            )

        callback.message.edit_text.assert_called_once_with(templates.TOO_LATE_TODAY)

    @pytest.mark.asyncio
    async def test_day4_with_available_time_slots(
        self,
        mock_callback,
        mock_user_service,
        mock_course_service,
    ):
        """День 4, есть доступные слоты времени."""
        from app.handlers.private import cycle_day_callback

        today = get_tashkent_now().isoformat()

        mock_user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})
        mock_course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "created_at": today,
            "status": "setup",
        })
        mock_course_service.update = AsyncMock()
        mock_course_service.set_expired = AsyncMock()

        callback = mock_callback(data="cycle_4")

        mock_keyboard = MagicMock()
        with patch("app.handlers.private.time_keyboard_today", return_value=mock_keyboard):
            await cycle_day_callback(
                callback=callback,
                course_service=mock_course_service,
                user_service=mock_user_service,
            )

        mock_course_service.update.assert_called_once()
        callback.message.edit_text.assert_called_once()
        # Проверяем что клавиатура передана
        call_kwargs = callback.message.edit_text.call_args[1]
        assert call_kwargs["reply_markup"] == mock_keyboard

    @pytest.mark.asyncio
    async def test_day1_tomorrow_start(
        self,
        mock_callback,
        mock_user_service,
        mock_course_service,
    ):
        """День 1-3 — начало завтра."""
        from app.handlers.private import cycle_day_callback

        today = get_tashkent_now().isoformat()

        mock_user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})
        mock_course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "created_at": today,
            "status": "setup",
        })
        mock_course_service.update = AsyncMock()
        mock_course_service.set_expired = AsyncMock()

        callback = mock_callback(data="cycle_1")

        mock_keyboard = MagicMock()
        with patch("app.handlers.private.time_keyboard", return_value=mock_keyboard):
            await cycle_day_callback(
                callback=callback,
                course_service=mock_course_service,
                user_service=mock_user_service,
            )

        mock_course_service.update.assert_called_once()
        # Проверяем что cycle_day=1 передан
        call_kwargs = mock_course_service.update.call_args[1]
        assert call_kwargs["cycle_day"] == 1


class TestTimeCallback:
    """Тесты для time_callback."""

    @pytest.mark.asyncio
    async def test_expired_course_created_yesterday(
        self,
        mock_callback,
        mock_user_service,
        mock_course_service,
        mock_manager_service,
        mock_topic_service,
    ):
        """Курс создан вчера — показать expired."""
        from app.handlers.private import time_callback

        yesterday = (get_tashkent_now() - timedelta(days=1)).isoformat()

        mock_user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})
        mock_course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "created_at": yesterday,
            "status": "setup",
        })
        mock_course_service.set_expired = AsyncMock()

        callback = mock_callback(data="time_12_00")

        await time_callback(
            callback=callback,
            course_service=mock_course_service,
            user_service=mock_user_service,
            manager_service=mock_manager_service,
            topic_service=mock_topic_service,
        )

        mock_course_service.set_expired.assert_called_once_with(1)
        callback.message.edit_text.assert_called_once_with(
            templates.TOO_LATE_REGISTRATION_EXPIRED
        )

    @pytest.mark.asyncio
    async def test_successful_registration(
        self,
        mock_callback,
        mock_user_service,
        mock_course_service,
        mock_manager_service,
        mock_topic_service,
    ):
        """Успешная регистрация."""
        from app.handlers.private import time_callback

        today = get_tashkent_now().isoformat()

        mock_user_service.get_by_telegram_id = AsyncMock(return_value={
            "id": 1,
            "name": "Тестова Мария",
            "manager_id": 1,
        })
        mock_course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "created_at": today,
            "status": "setup",
            "start_date": "2026-01-15",
            "cycle_day": 1,
        })
        mock_course_service.update = AsyncMock()
        mock_course_service.set_expired = AsyncMock()
        mock_manager_service.get_by_id = AsyncMock(return_value={"name": "Manager"})
        mock_topic_service.create_topic = AsyncMock(return_value=123)
        mock_topic_service.send_registration_info = AsyncMock(return_value=456)
        mock_user_service.set_topic_id = AsyncMock()

        callback = mock_callback(data="time_14_30")

        await time_callback(
            callback=callback,
            course_service=mock_course_service,
            user_service=mock_user_service,
            manager_service=mock_manager_service,
            topic_service=mock_topic_service,
        )

        # Проверяем что курс обновлён
        mock_course_service.update.assert_called()
        first_call = mock_course_service.update.call_args_list[0]
        assert first_call[1]["intake_time"] == "14:30"
        assert first_call[1]["status"] == "active"

        # Проверяем что топик создан
        mock_topic_service.create_topic.assert_called_once()

        # Проверяем что сообщение отправлено
        callback.message.edit_text.assert_called_once()
        call_args = callback.message.edit_text.call_args[0][0]
        assert "14:30" in call_args


class TestStartWithLink:
    """Тесты для start_with_link."""

    @pytest.mark.asyncio
    async def test_invalid_link(
        self,
        mock_message,
        mock_course_service,
        mock_user_service,
    ):
        """Невалидная ссылка."""
        from app.handlers.private import start_with_link

        mock_course_service.get_by_invite_code = AsyncMock(return_value=None)

        message = mock_message(text="/start abc123")
        command = MagicMock()
        command.args = "abc123"

        await start_with_link(
            message=message,
            command=command,
            course_service=mock_course_service,
            user_service=mock_user_service,
        )

        message.answer.assert_called_once_with(templates.LINK_INVALID)

    @pytest.mark.asyncio
    async def test_link_already_used(
        self,
        mock_message,
        mock_course_service,
        mock_user_service,
    ):
        """Ссылка уже использована."""
        from app.handlers.private import start_with_link

        mock_course_service.get_by_invite_code = AsyncMock(return_value={
            "id": 1,
            "invite_used": True,
        })

        message = mock_message(text="/start abc123")
        command = MagicMock()
        command.args = "abc123"

        await start_with_link(
            message=message,
            command=command,
            course_service=mock_course_service,
            user_service=mock_user_service,
        )

        message.answer.assert_called_once_with(templates.LINK_USED)

    @pytest.mark.asyncio
    async def test_valid_link_welcome(
        self,
        mock_message,
        mock_course_service,
        mock_user_service,
    ):
        """Валидная ссылка — показать приветствие."""
        from app.handlers.private import start_with_link

        mock_course_service.get_by_invite_code = AsyncMock(return_value={
            "id": 1,
            "user_id": 1,
            "invite_used": False,
        })
        mock_course_service.mark_invite_used = AsyncMock()
        mock_user_service.set_telegram_id = AsyncMock()
        mock_user_service.get_by_id = AsyncMock(return_value={"name": "Тестова Мария"})

        message = mock_message(text="/start abc123")
        command = MagicMock()
        command.args = "abc123"

        await start_with_link(
            message=message,
            command=command,
            course_service=mock_course_service,
            user_service=mock_user_service,
        )

        mock_course_service.mark_invite_used.assert_called_once_with(1)
        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Тестова Мария" in call_args