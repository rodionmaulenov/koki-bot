"""Тесты для handlers/video.py."""
import pytest
from unittest.mock import AsyncMock, patch

from app import templates


class TestVideoHandlerValidation:
    """Тесты валидации в video_handler."""

    @pytest.mark.asyncio
    async def test_no_user(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
    ):
        """User не найден."""
        from app.handlers.video import video_handler

        message = mock_video_message(user_id=999999999)

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=course_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
            manager_service=manager_service,
            gemini_service=mock_gemini_confirmed,
            bot=bot,
        )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert call_text == templates.ERROR_NO_USER

    @pytest.mark.asyncio
    async def test_no_active_course(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
    ):
        """Нет активного курса."""
        from app.handlers.video import video_handler

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=course_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
            manager_service=manager_service,
            gemini_service=mock_gemini_confirmed,
            bot=bot,
        )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert call_text == templates.VIDEO_NO_ACTIVE_COURSE

    @pytest.mark.asyncio
    async def test_course_not_started(
            self,
            mock_video_message,
            user_service,
            course_service,
            intake_logs_service,
            topic_service,
            manager_service,
            mock_gemini_confirmed,
            bot,
            test_user_with_telegram,
            test_future_course,  # ← используем fixture
    ):
        """Курс ещё не начался."""
        from app.handlers.video import video_handler

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=course_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
            manager_service=manager_service,
            gemini_service=mock_gemini_confirmed,
            bot=bot,
        )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert call_text == templates.VIDEO_COURSE_NOT_STARTED

    @pytest.mark.asyncio
    async def test_only_circles_allowed(
        self,
        mock_regular_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
        test_active_course,
    ):
        """Обычное видео без разрешения."""
        from app.handlers.video import video_handler

        message = mock_regular_video_message(user_id=test_user_with_telegram["telegram_id"])

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=course_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
            manager_service=manager_service,
            gemini_service=mock_gemini_confirmed,
            bot=bot,
        )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert call_text == templates.VIDEO_ONLY_CIRCLES

    @pytest.mark.asyncio
    async def test_already_sent_today(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
        test_active_course,
    ):
        """Уже отправила видео сегодня."""
        from app.handlers.video import video_handler

        # Создаём запись что видео уже принято
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=test_active_course["current_day"],
            status="taken",
            video_file_id="existing_video",
        )

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=course_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
            manager_service=manager_service,
            gemini_service=mock_gemini_confirmed,
            bot=bot,
        )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert call_text == templates.VIDEO_ALREADY_SENT

    @pytest.mark.asyncio
    async def test_pending_review_blocks_second_video(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
        test_active_course,
    ):
        """Видео на проверке — второе не принимается."""
        from app.handlers.video import video_handler

        # Создаём запись что видео на проверке
        await intake_logs_service.create(
            course_id=test_active_course["id"],
            day=test_active_course["current_day"],
            status="pending_review",
            video_file_id="pending_video",
        )

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=course_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
            manager_service=manager_service,
            gemini_service=mock_gemini_confirmed,
            bot=bot,
        )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert call_text == templates.VIDEO_ALREADY_SENT

    @pytest.mark.asyncio
    async def test_too_early(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
        test_active_course_too_early,
    ):
        """Слишком рано для видео."""
        from app.handlers.video import video_handler

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        await video_handler(
            message=message,
            user_service=user_service,
            course_service=course_service,
            intake_logs_service=intake_logs_service,
            topic_service=topic_service,
            manager_service=manager_service,
            gemini_service=mock_gemini_confirmed,
            bot=bot,
        )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert "рано" in call_text.lower() or "откроется" in call_text.lower()


class TestVideoHandlerGemini:
    """Тесты обработки видео через Gemini."""

    @pytest.mark.asyncio
    async def test_gemini_confirmed(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
        test_active_course,
    ):
        """Gemini подтвердил видео."""
        from app.handlers.video import video_handler
        from app.services.gemini import GeminiService

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        # Мокаем download_video контекстный менеджер
        with patch.object(GeminiService, 'download_video') as mock_download:
            mock_download.return_value.__aenter__ = AsyncMock(return_value="/tmp/test.mp4")
            mock_download.return_value.__aexit__ = AsyncMock(return_value=None)

            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=intake_logs_service,
                topic_service=topic_service,
                manager_service=manager_service,
                gemini_service=mock_gemini_confirmed,
                bot=bot,
            )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert "принят" in call_text.lower()

    @pytest.mark.asyncio
    async def test_gemini_pending(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_pending,
        bot,
        test_user_with_telegram,
        test_active_course,
    ):
        """Gemini не уверен — на проверку менеджеру."""
        from app.handlers.video import video_handler
        from app.services.gemini import GeminiService

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        with patch.object(GeminiService, 'download_video') as mock_download:
            mock_download.return_value.__aenter__ = AsyncMock(return_value="/tmp/test.mp4")
            mock_download.return_value.__aexit__ = AsyncMock(return_value=None)

            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=intake_logs_service,
                topic_service=topic_service,
                manager_service=manager_service,
                gemini_service=mock_gemini_pending,
                bot=bot,
            )

        message.answer.assert_called_once()
        call_text = message.answer.call_args[0][0]
        assert call_text == templates.VIDEO_PENDING_REVIEW

class TestExtendedCourseLogic:
    """Тесты для логики продлённого курса (total_days > 21)."""

    @pytest.mark.asyncio
    async def test_course_continues_after_day_21_if_extended(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Курс не завершается на 21 дне если total_days = 42."""
        from app.handlers.video import video_handler
        from app.services.gemini import GeminiService

        # Устанавливаем день 21 и total_days = 42
        await supabase.table("courses") \
            .update({"current_day": 21, "total_days": 42}) \
            .eq("id", test_active_course["id"]) \
            .execute()

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        with patch.object(GeminiService, 'download_video') as mock_download:
            mock_download.return_value.__aenter__ = AsyncMock(return_value="/tmp/test.mp4")
            mock_download.return_value.__aexit__ = AsyncMock(return_value=None)

            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=intake_logs_service,
                topic_service=topic_service,
                manager_service=manager_service,
                gemini_service=mock_gemini_confirmed,
                bot=bot,
            )

        # Проверяем что курс НЕ завершён
        course = await supabase.table("courses") \
            .select("status, current_day") \
            .eq("id", test_active_course["id"]) \
            .single() \
            .execute()

        assert course.data["status"] == "active"
        assert course.data["current_day"] == 22

    @pytest.mark.asyncio
    async def test_course_completes_at_total_days(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        topic_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Курс завершается когда current_day достигает total_days."""
        from app.handlers.video import video_handler
        from app.services.gemini import GeminiService
        from app import templates

        # Устанавливаем день 21 и total_days = 21 (стандартный курс)
        await supabase.table("courses") \
            .update({"current_day": 21, "total_days": 21}) \
            .eq("id", test_active_course["id"]) \
            .execute()

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        with patch.object(GeminiService, 'download_video') as mock_download:
            mock_download.return_value.__aenter__ = AsyncMock(return_value="/tmp/test.mp4")
            mock_download.return_value.__aexit__ = AsyncMock(return_value=None)

            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=intake_logs_service,
                topic_service=topic_service,
                manager_service=manager_service,
                gemini_service=mock_gemini_confirmed,
                bot=bot,
            )

        # Проверяем что курс завершён
        course = await supabase.table("courses") \
            .select("status, current_day") \
            .eq("id", test_active_course["id"]) \
            .single() \
            .execute()

        assert course.data["status"] == "completed"
        assert course.data["current_day"] == 21

        # Проверяем сообщение
        call_text = message.answer.call_args[0][0]
        assert call_text == templates.VIDEO_COURSE_FINISHED

    @pytest.mark.asyncio
    async def test_full_closure_sequence_on_course_complete(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Выполняет полную последовательность закрытия топика при завершении курса."""
        from app.handlers.video import video_handler
        from app.services.gemini import GeminiService
        from unittest.mock import MagicMock

        # Устанавливаем topic_id и registration_message_id
        topic_id = 12345
        registration_message_id = 999

        await supabase.table("users") \
            .update({"topic_id": topic_id}) \
            .eq("id", test_user_with_telegram["id"]) \
            .execute()

        await supabase.table("courses") \
            .update({
                "current_day": 21,
                "total_days": 21,
                "registration_message_id": registration_message_id,
            }) \
            .eq("id", test_active_course["id"]) \
            .execute()

        # Mock topic_service с всеми методами
        mock_topic_service = MagicMock()
        mock_topic_service.send_video = AsyncMock()
        mock_topic_service.rename_topic_on_close = AsyncMock()
        mock_topic_service.remove_registration_buttons = AsyncMock()
        mock_topic_service.send_closure_message = AsyncMock()
        mock_topic_service.close_topic = AsyncMock()

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        with patch.object(GeminiService, 'download_video') as mock_download:
            mock_download.return_value.__aenter__ = AsyncMock(return_value="/tmp/test.mp4")
            mock_download.return_value.__aexit__ = AsyncMock(return_value=None)

            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=intake_logs_service,
                topic_service=mock_topic_service,
                manager_service=manager_service,
                gemini_service=mock_gemini_confirmed,
                bot=bot,
            )

        # Проверяем полную последовательность закрытия
        mock_topic_service.rename_topic_on_close.assert_called_once()
        mock_topic_service.remove_registration_buttons.assert_called_once()
        mock_topic_service.send_closure_message.assert_called_once()
        mock_topic_service.close_topic.assert_called_once()

        # Проверяем параметры rename
        rename_call = mock_topic_service.rename_topic_on_close.call_args
        assert rename_call.kwargs["topic_id"] == topic_id
        assert rename_call.kwargs["status"] == "completed"
        assert rename_call.kwargs["completed_days"] == 21
        assert rename_call.kwargs["total_days"] == 21

        # Проверяем параметры closure message
        closure_call = mock_topic_service.send_closure_message.call_args
        assert closure_call.kwargs["status"] == "completed"

    @pytest.mark.asyncio
    async def test_skips_buttons_removal_if_no_message_id(
        self,
        mock_video_message,
        user_service,
        course_service,
        intake_logs_service,
        manager_service,
        mock_gemini_confirmed,
        bot,
        test_user_with_telegram,
        test_active_course,
        supabase,
    ):
        """Пропускает удаление кнопок если нет registration_message_id."""
        from app.handlers.video import video_handler
        from app.services.gemini import GeminiService
        from unittest.mock import MagicMock

        # Устанавливаем topic_id БЕЗ registration_message_id
        topic_id = 12345
        await supabase.table("users") \
            .update({"topic_id": topic_id}) \
            .eq("id", test_user_with_telegram["id"]) \
            .execute()

        await supabase.table("courses") \
            .update({"current_day": 21, "total_days": 21}) \
            .eq("id", test_active_course["id"]) \
            .execute()

        mock_topic_service = MagicMock()
        mock_topic_service.send_video = AsyncMock()
        mock_topic_service.rename_topic_on_close = AsyncMock()
        mock_topic_service.remove_registration_buttons = AsyncMock()
        mock_topic_service.send_closure_message = AsyncMock()
        mock_topic_service.close_topic = AsyncMock()

        message = mock_video_message(user_id=test_user_with_telegram["telegram_id"])

        with patch.object(GeminiService, 'download_video') as mock_download:
            mock_download.return_value.__aenter__ = AsyncMock(return_value="/tmp/test.mp4")
            mock_download.return_value.__aexit__ = AsyncMock(return_value=None)

            await video_handler(
                message=message,
                user_service=user_service,
                course_service=course_service,
                intake_logs_service=intake_logs_service,
                topic_service=mock_topic_service,
                manager_service=manager_service,
                gemini_service=mock_gemini_confirmed,
                bot=bot,
            )

        # remove_registration_buttons НЕ должен вызываться
        mock_topic_service.remove_registration_buttons.assert_not_called()

        # Остальные методы должны вызываться
        mock_topic_service.rename_topic_on_close.assert_called_once()
        mock_topic_service.send_closure_message.assert_called_once()
        mock_topic_service.close_topic.assert_called_once()