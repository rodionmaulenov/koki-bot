"""Тесты для handlers/video.py."""
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app import templates


@pytest.fixture
def mock_gemini_service():
    """Mock GeminiService."""
    service = MagicMock()
    service.verify_video = AsyncMock(return_value={
        "status": "confirmed",
        "confidence": 95,
        "reason": "",
    })
    return service


@pytest.fixture
def mock_video_message():
    """Фабрика для создания mock video message."""
    def _create(user_id: int = 123456, is_circle: bool = True):
        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = user_id
        message.answer = AsyncMock()

        if is_circle:
            message.video_note = MagicMock()
            message.video_note.file_id = "test_video_note_id"
            message.video = None
        else:
            message.video = MagicMock()
            message.video.file_id = "test_video_id"
            message.video_note = None

        return message
    return _create


class TestVideoHandlerNoUser:
    """Тесты когда пользователь не найден."""

    @pytest.mark.asyncio
    async def test_no_user_error(self, mock_video_message, mock_gemini_service, bot):
        """Ошибка если пользователь не найден."""
        from app.handlers.video import video_handler

        message = mock_video_message(user_id=999999)

        # User service возвращает None
        user_service = MagicMock()
        user_service.get_by_telegram_id = AsyncMock(return_value=None)

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=MagicMock(),
            intake_logs_service=MagicMock(),
            topic_service=MagicMock(),
            manager_service=MagicMock(),
            gemini_service=mock_gemini_service,
            bot=bot,
        )

        message.answer.assert_called_once_with(templates.ERROR_NO_USER)


class TestVideoHandlerNoCourse:
    """Тесты когда нет активного курса."""

    @pytest.mark.asyncio
    async def test_no_active_course_error(self, mock_video_message, mock_gemini_service, bot):
        """Ошибка если нет активного курса."""
        from app.handlers.video import video_handler

        message = mock_video_message()

        user_service = MagicMock()
        user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1, "telegram_id": 123456})

        course_service = MagicMock()
        course_service.get_active_by_user_id = AsyncMock(return_value=None)

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=course_service,
            intake_logs_service=MagicMock(),
            topic_service=MagicMock(),
            manager_service=MagicMock(),
            gemini_service=mock_gemini_service,
            bot=bot,
        )

        message.answer.assert_called_once_with(templates.VIDEO_NO_ACTIVE_COURSE)

    @pytest.mark.asyncio
    async def test_course_not_active_status(self, mock_video_message, mock_gemini_service, bot):
        """Ошибка если курс не в статусе active."""
        from app.handlers.video import video_handler

        message = mock_video_message()

        user_service = MagicMock()
        user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})

        course_service = MagicMock()
        course_service.get_active_by_user_id = AsyncMock(return_value={"id": 1, "status": "setup"})

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=course_service,
            intake_logs_service=MagicMock(),
            topic_service=MagicMock(),
            manager_service=MagicMock(),
            gemini_service=mock_gemini_service,
            bot=bot,
        )

        message.answer.assert_called_once_with(templates.VIDEO_NO_ACTIVE_COURSE)


class TestVideoHandlerCourseNotStarted:
    """Тесты когда курс ещё не начался."""

    @pytest.mark.asyncio
    async def test_course_not_started(self, mock_video_message, mock_gemini_service, bot):
        """Ошибка если курс ещё не начался."""
        from app.handlers.video import video_handler

        message = mock_video_message()

        user_service = MagicMock()
        user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})

        # Курс начинается завтра
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        course_service = MagicMock()
        course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "status": "active",
            "start_date": tomorrow,
        })

        with patch("app.handlers.video.get_tashkent_now") as mock_now:
            mock_now.return_value.date.return_value = date.today()

            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=MagicMock(),
                topic_service=MagicMock(),
                manager_service=MagicMock(),
                gemini_service=mock_gemini_service,
                bot=bot,
            )

        message.answer.assert_called_once_with(templates.VIDEO_COURSE_NOT_STARTED)


class TestVideoHandlerOnlyCircles:
    """Тесты для проверки типа видео."""

    @pytest.mark.asyncio
    async def test_regular_video_not_allowed(self, mock_video_message, mock_gemini_service, bot):
        """Ошибка если обычное видео не разрешено."""
        from app.handlers.video import video_handler

        # Обычное видео, не кружочек
        message = mock_video_message(is_circle=False)

        user_service = MagicMock()
        user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})

        today = date.today().isoformat()
        course_service = MagicMock()
        course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "status": "active",
            "start_date": today,
            "allow_video": False,  # Обычное видео не разрешено
        })

        with patch("app.handlers.video.get_tashkent_now") as mock_now:
            mock_now.return_value.date.return_value = date.today()

            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=MagicMock(),
                topic_service=MagicMock(),
                manager_service=MagicMock(),
                gemini_service=mock_gemini_service,
                bot=bot,
            )

        message.answer.assert_called_once_with(templates.VIDEO_ONLY_CIRCLES)


class TestVideoHandlerAlreadySent:
    """Тесты когда видео уже отправлено сегодня."""

    @pytest.mark.asyncio
    async def test_already_sent_today(self, mock_video_message, mock_gemini_service, bot):
        """Ошибка если уже отправила видео сегодня."""
        from app.handlers.video import video_handler

        message = mock_video_message()

        user_service = MagicMock()
        user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})

        today = date.today().isoformat()
        course_service = MagicMock()
        course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "status": "active",
            "start_date": today,
            "current_day": 5,
        })

        intake_logs_service = MagicMock()
        intake_logs_service.get_by_course_and_day = AsyncMock(return_value={"id": 1})  # Уже есть запись

        with patch("app.handlers.video.get_tashkent_now") as mock_now:
            mock_now.return_value.date.return_value = date.today()

            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=intake_logs_service,
                topic_service=MagicMock(),
                manager_service=MagicMock(),
                gemini_service=mock_gemini_service,
                bot=bot,
            )

        message.answer.assert_called_once_with(templates.VIDEO_ALREADY_SENT)


class TestVideoHandlerTooEarly:
    """Тесты когда слишком рано для видео."""

    @pytest.mark.asyncio
    async def test_too_early(self, mock_video_message, mock_gemini_service, bot):
        """Ошибка если слишком рано."""
        from app.handlers.video import video_handler

        message = mock_video_message()

        user_service = MagicMock()
        user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1})

        today = date.today().isoformat()
        course_service = MagicMock()
        course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "status": "active",
            "start_date": today,
            "current_day": 1,
            "intake_time": "15:00",
        })

        intake_logs_service = MagicMock()
        intake_logs_service.get_by_course_and_day = AsyncMock(return_value=None)

        with patch("app.handlers.video.get_tashkent_now") as mock_now:
            mock_now.return_value.date.return_value = date.today()

        with patch("app.handlers.video.is_too_early", return_value=(True, "14:50")):
            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=intake_logs_service,
                topic_service=MagicMock(),
                manager_service=MagicMock(),
                gemini_service=mock_gemini_service,
                bot=bot,
            )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert "14:50" in call_text


class TestVideoHandlerSuccess:
    """Тесты успешной обработки видео."""

    @pytest.mark.asyncio
    async def test_video_confirmed(self, mock_video_message, bot):
        """Видео подтверждено Gemini."""
        from app.handlers.video import video_handler
        from contextlib import asynccontextmanager

        message = mock_video_message()

        user_service = MagicMock()
        user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1, "topic_id": 123, "manager_id": 1})

        today = date.today().isoformat()
        course_service = MagicMock()
        course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "status": "active",
            "start_date": today,
            "current_day": 1,
            "intake_time": "12:00",
            "total_days": 21,
        })
        course_service.update = AsyncMock()

        intake_logs_service = MagicMock()
        intake_logs_service.get_by_course_and_day = AsyncMock(return_value=None)
        intake_logs_service.create = AsyncMock()

        topic_service = MagicMock()
        topic_service.send_video = AsyncMock()
        topic_service.update_progress = AsyncMock()

        manager_service = MagicMock()
        manager_service.get_by_id = AsyncMock(return_value={"name": "Test Manager"})

        gemini_service = MagicMock()
        gemini_service.verify_video = AsyncMock(return_value={
            "status": "confirmed",
            "confidence": 95,
            "reason": "",
        })

        @asynccontextmanager
        async def mock_download(*args, **kwargs):
            yield "/tmp/test_video.mp4"

        with patch("app.handlers.video.get_tashkent_now") as mock_now:
            mock_now.return_value.date.return_value = date.today()

        with patch("app.handlers.video.is_too_early", return_value=(False, "")):
            with patch("app.handlers.video.GeminiService.download_video", mock_download):
                await video_handler(
                    message=message,
                    user_service=user_service,
                    course_service=course_service,
                    intake_logs_service=intake_logs_service,
                    topic_service=topic_service,
                    manager_service=manager_service,
                    gemini_service=gemini_service,
                    bot=bot,
                )

        # Проверяем что intake_log создан
        intake_logs_service.create.assert_called_once()
        create_call = intake_logs_service.create.call_args
        assert create_call.kwargs["status"] == "taken"
        assert create_call.kwargs["verified_by"] == "gemini"

        # Проверяем что current_day обновлён
        course_service.update.assert_called()

        # Проверяем ответ
        message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_video_pending_review(self, mock_video_message, bot):
        """Видео отправлено на проверку менеджеру."""
        from app.handlers.video import video_handler
        from contextlib import asynccontextmanager

        message = mock_video_message()

        user_service = MagicMock()
        user_service.get_by_telegram_id = AsyncMock(return_value={"id": 1, "topic_id": 123, "manager_id": 1})

        today = date.today().isoformat()
        course_service = MagicMock()
        course_service.get_active_by_user_id = AsyncMock(return_value={
            "id": 1,
            "status": "active",
            "start_date": today,
            "current_day": 1,
            "intake_time": "12:00",
            "total_days": 21,
        })

        intake_logs_service = MagicMock()
        intake_logs_service.get_by_course_and_day = AsyncMock(return_value=None)
        intake_logs_service.create = AsyncMock()

        topic_service = MagicMock()
        topic_service.send_video = AsyncMock()
        topic_service.send_review_buttons = AsyncMock()

        gemini_service = MagicMock()
        gemini_service.verify_video = AsyncMock(return_value={
            "status": "pending",
            "confidence": 50,
            "reason": "Не видно таблетку",
        })

        @asynccontextmanager
        async def mock_download(*args, **kwargs):
            yield "/tmp/test_video.mp4"

        with patch("app.handlers.video.get_tashkent_now") as mock_now:
            mock_now.return_value.date.return_value = date.today()

        with patch("app.handlers.video.is_too_early", return_value=(False, "")):
            with patch("app.handlers.video.GeminiService.download_video", mock_download):
                await video_handler(
                    message=message,
                    user_service=user_service,
                    course_service=course_service,
                    intake_logs_service=intake_logs_service,
                    topic_service=topic_service,
                    manager_service=MagicMock(),
                    gemini_service=gemini_service,
                    bot=bot,
                )

        # Проверяем статус pending_review
        intake_logs_service.create.assert_called_once()
        create_call = intake_logs_service.create.call_args
        assert create_call.kwargs["status"] == "pending_review"
        assert create_call.kwargs["verified_by"] is None

        # Кнопки проверки отправлены
        topic_service.send_review_buttons.assert_called_once()

        # Ответ пользователю
        message.answer.assert_called_once_with(templates.VIDEO_PENDING_REVIEW)