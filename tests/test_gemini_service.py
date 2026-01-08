"""Тесты для GeminiService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.gemini import GeminiService


class TestGeminiServiceParseResponse:
    """Тесты парсинга ответа от Gemini."""

    def test_parses_valid_json(self):
        """Парсит валидный JSON."""
        response = '{"is_taking_pill": true, "confidence": 85, "reason": "Видно приём"}'

        result = GeminiService._parse_response(response)

        assert result["is_taking_pill"] is True
        assert result["confidence"] == 85
        assert result["reason"] == "Видно приём"

    def test_parses_json_with_markdown(self):
        """Парсит JSON обёрнутый в markdown."""
        response = '```json\n{"is_taking_pill": true, "confidence": 90, "reason": "OK"}\n```'

        result = GeminiService._parse_response(response)

        assert result["is_taking_pill"] is True
        assert result["confidence"] == 90

    def test_parses_json_with_backticks(self):
        """Парсит JSON с простыми backticks."""
        response = '```\n{"is_taking_pill": false, "confidence": 30, "reason": "Не видно"}\n```'

        result = GeminiService._parse_response(response)

        assert result["is_taking_pill"] is False
        assert result["confidence"] == 30

    def test_handles_invalid_json(self):
        """Обрабатывает невалидный JSON."""
        response = 'not a json at all'

        result = GeminiService._parse_response(response)

        assert result["is_taking_pill"] is False
        assert result["confidence"] == 0
        assert "Не удалось распознать" in result["reason"]

    def test_handles_missing_fields(self):
        """Обрабатывает отсутствующие поля."""
        response = '{"is_taking_pill": true}'

        result = GeminiService._parse_response(response)

        assert result["is_taking_pill"] is True
        assert result["confidence"] == 0
        assert result["reason"] == ""


class TestGeminiServiceDetermineStatus:
    """Тесты определения статуса."""

    def test_confirmed_high_confidence(self):
        """Confirmed при высокой уверенности."""
        service = GeminiService(api_key="fake")

        status = service._determine_status(is_taking_pill=True, confidence=85)

        assert status == "confirmed"

    def test_confirmed_at_threshold(self):
        """Confirmed при пороговой уверенности (70)."""
        service = GeminiService(api_key="fake")

        status = service._determine_status(is_taking_pill=True, confidence=70)

        assert status == "confirmed"

    def test_pending_low_confidence(self):
        """Pending при низкой уверенности."""
        service = GeminiService(api_key="fake")

        status = service._determine_status(is_taking_pill=True, confidence=69)

        assert status == "pending"

    def test_pending_not_taking_pill(self):
        """Pending если не видно приём."""
        service = GeminiService(api_key="fake")

        status = service._determine_status(is_taking_pill=False, confidence=90)

        assert status == "pending"

    def test_pending_zero_confidence(self):
        """Pending при нулевой уверенности."""
        service = GeminiService(api_key="fake")

        status = service._determine_status(is_taking_pill=True, confidence=0)

        assert status == "pending"


class TestGeminiServiceVerifyVideo:
    """Тесты верификации видео."""

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_file(self):
        """Возвращает ошибку для несуществующего файла."""
        service = GeminiService(api_key="fake")

        result = await service.verify_video("/nonexistent/path/video.mp4")

        assert result["is_taking_pill"] is False
        assert result["confidence"] == 0
        assert result["status"] == "pending"
        assert "Ошибка" in result["reason"]

    @pytest.mark.asyncio
    async def test_successful_verification(self, tmp_path):
        """Успешная верификация видео."""
        # Создаём фейковый файл
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video content")

        # Мокаем Gemini клиент
        mock_client = MagicMock()

        # Мокаем upload
        mock_video_file = MagicMock()
        mock_video_file.name = "files/123"
        mock_video_file.state.name = "ACTIVE"
        mock_client.files.upload.return_value = mock_video_file
        mock_client.files.get.return_value = mock_video_file
        mock_client.files.delete.return_value = None

        # Мокаем generate_content
        mock_response = MagicMock()
        mock_response.text = '{"is_taking_pill": true, "confidence": 85, "reason": "OK"}'
        mock_client.models.generate_content.return_value = mock_response

        service = GeminiService(api_key="fake")
        service.client = mock_client

        result = await service.verify_video(str(video_file))

        assert result["is_taking_pill"] is True
        assert result["confidence"] == 85
        assert result["status"] == "confirmed"


class TestGeminiServiceDownloadVideo:
    """Тесты скачивания видео."""

    @pytest.mark.asyncio
    async def test_downloads_and_cleans_up(self, bot, tmp_path):
        """Скачивает видео и удаляет после использования."""
        # Мокаем bot методы
        mock_file = MagicMock()
        mock_file.file_path = "videos/test.mp4"
        bot.get_file = AsyncMock(return_value=mock_file)
        bot.download_file = AsyncMock()

        # Патчим TEMP_DIR
        with patch("app.services.gemini.TEMP_DIR", tmp_path):
            async with GeminiService.download_video(bot, "file_id_123") as video_path:
                # Внутри контекста файл должен существовать (мокнутый)
                assert "file_id_123.mp4" in video_path

            # После выхода файл удаляется (но его и не было реально)
            bot.get_file.assert_called_once_with("file_id_123")
            bot.download_file.assert_called_once()


class TestGeminiServiceThreshold:
    """Тесты порогового значения."""

    def test_default_threshold(self):
        """Порог по умолчанию 70."""
        service = GeminiService(api_key="fake")

        assert service.CONFIDENCE_THRESHOLD == 70

    def test_boundary_values(self):
        """Граничные значения порога."""
        service = GeminiService(api_key="fake")

        # Ровно на пороге — confirmed
        assert service._determine_status(True, 70) == "confirmed"

        # На 1 ниже — pending
        assert service._determine_status(True, 69) == "pending"