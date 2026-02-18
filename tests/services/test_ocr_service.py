"""Tests for OCRService — unit tests with mocked Bot and GeminiService.

Key logic tested:
- Full pipeline: download → preprocess → Gemini → result
- Download failure → OCRServerError
- Gemini APIError → OCRServerError(e.message)
- Gemini ValueError/JSONDecodeError → OCRServerError(str(e))
- Each process_* delegates to correct Gemini method
- preprocess_image runs in thread via asyncio.to_thread
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from google.genai import errors as genai_errors

from models.ocr import CardResult, OCRServerError, PassportResult, ReceiptResult
from services.ocr_service import OCRService


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_gemini() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock()

    async def _fake_download(file_id, destination):
        destination.write(b"fake-image-bytes")

    bot.download = AsyncMock(side_effect=_fake_download)
    return bot


@pytest.fixture
def ocr(mock_gemini, mock_bot) -> OCRService:
    return OCRService(gemini=mock_gemini, bot=mock_bot)


@pytest.fixture
def patch_to_thread():
    """Patch asyncio.to_thread to run synchronously and return preprocessed bytes."""
    with patch(
        "asyncio.to_thread",
        new_callable=AsyncMock,
        return_value=b"preprocessed-bytes",
    ) as mock:
        yield mock


# =============================================================================
# DOWNLOAD AND PREPROCESS
# =============================================================================


class TestDownloadAndPreprocess:
    async def test_success(
        self, ocr: OCRService, mock_bot: AsyncMock, patch_to_thread,
    ):
        """Happy path: download → preprocess_image → return bytes."""
        result = await ocr._download_and_preprocess("file_123")

        mock_bot.download.assert_called_once()
        assert mock_bot.download.call_args[0][0] == "file_123"
        assert result == b"preprocessed-bytes"

    async def test_download_failure_raises_ocr_server_error(
        self, ocr: OCRService, mock_bot: AsyncMock,
    ):
        """Bot download fails → OCRServerError with 'File download failed'."""
        mock_bot.download = AsyncMock(side_effect=ConnectionError("Network down"))

        with pytest.raises(OCRServerError, match="File download failed"):
            await ocr._download_and_preprocess("file_123")

    async def test_preprocess_called_in_thread(
        self, ocr: OCRService, patch_to_thread,
    ):
        """preprocess_image is called via asyncio.to_thread (CPU-bound work)."""
        await ocr._download_and_preprocess("file_123")

        patch_to_thread.assert_called_once()
        args = patch_to_thread.call_args[0]
        # First arg is the function, second is the image bytes
        from utils.image import preprocess_image
        assert args[0] is preprocess_image
        assert args[1] == b"fake-image-bytes"


# =============================================================================
# CALL GEMINI
# =============================================================================


class TestCallGemini:
    async def test_success_returns_result(self, ocr: OCRService):
        """Gemini method returns result → same object returned."""
        expected = PassportResult(
            is_document=True, last_name="TEST",
            first_name="USER", patronymic=None, birth_date=None,
        )
        method = AsyncMock(return_value=expected)

        result = await ocr._call_gemini(method, b"img", "passport", "f1")

        assert result is expected
        method.assert_called_once_with(b"img")

    async def test_api_error_wrapped(self, ocr: OCRService):
        """genai APIError → OCRServerError with e.message (not str(e))."""
        api_error = genai_errors.APIError(
            429, {"error": {"message": "Rate limit exceeded"}},
        )
        method = AsyncMock(side_effect=api_error)

        with pytest.raises(OCRServerError) as exc_info:
            await ocr._call_gemini(method, b"img", "passport", "f1")

        # Must be exactly e.message, NOT str(e) which includes "429 None. {...}"
        assert str(exc_info.value) == "Rate limit exceeded"

    async def test_value_error_wrapped(self, ocr: OCRService):
        """ValueError → OCRServerError with str(e)."""
        method = AsyncMock(side_effect=ValueError("Gemini returned empty response"))

        with pytest.raises(OCRServerError, match="Gemini returned empty response"):
            await ocr._call_gemini(method, b"img", "passport", "f1")

    async def test_json_decode_error_wrapped(self, ocr: OCRService):
        """JSONDecodeError → OCRServerError."""
        method = AsyncMock(
            side_effect=json.JSONDecodeError("Expecting value", "doc", 0),
        )

        with pytest.raises(OCRServerError):
            await ocr._call_gemini(method, b"img", "receipt", "f1")


# =============================================================================
# PROCESS METHODS — DELEGATION
# =============================================================================


class TestProcessPassport:
    async def test_full_pipeline(
        self, ocr: OCRService, mock_gemini: AsyncMock, patch_to_thread,
    ):
        """download → preprocess → gemini.process_passport → PassportResult."""
        expected = PassportResult(
            is_document=True, last_name="IVANOVA",
            first_name="MARINA", patronymic=None, birth_date="15.06.2000",
        )
        mock_gemini.process_passport.return_value = expected

        result = await ocr.process_passport("file_abc")

        assert result is expected
        mock_gemini.process_passport.assert_called_once_with(b"preprocessed-bytes")

    async def test_delegates_to_correct_gemini_method(
        self, ocr: OCRService, mock_gemini: AsyncMock, patch_to_thread,
    ):
        """process_passport calls gemini.process_passport (not card/receipt)."""
        await ocr.process_passport("file_abc")

        mock_gemini.process_passport.assert_called_once()
        mock_gemini.process_card.assert_not_called()
        mock_gemini.process_receipt.assert_not_called()


class TestProcessCard:
    async def test_delegates_to_correct_gemini_method(
        self, ocr: OCRService, mock_gemini: AsyncMock, patch_to_thread,
    ):
        """process_card calls gemini.process_card."""
        expected = CardResult(
            is_document=True, card_number="8600123456789012",
            card_holder="IVANOVA",
        )
        mock_gemini.process_card.return_value = expected

        result = await ocr.process_card("file_abc")

        assert result is expected
        mock_gemini.process_card.assert_called_once()
        mock_gemini.process_passport.assert_not_called()


class TestProcessReceipt:
    async def test_delegates_to_correct_gemini_method(
        self, ocr: OCRService, mock_gemini: AsyncMock, patch_to_thread,
    ):
        """process_receipt calls gemini.process_receipt."""
        expected = ReceiptResult(is_document=True, has_kok=True, price=50000)
        mock_gemini.process_receipt.return_value = expected

        result = await ocr.process_receipt("file_abc")

        assert result is expected
        mock_gemini.process_receipt.assert_called_once()
        mock_gemini.process_passport.assert_not_called()


# =============================================================================
# ERROR PROPAGATION (full chain through public methods)
# =============================================================================


class TestErrorPropagation:
    async def test_download_error_through_process_passport(
        self, ocr: OCRService, mock_bot: AsyncMock,
    ):
        """Download fails → OCRServerError propagates from process_passport."""
        mock_bot.download = AsyncMock(side_effect=TimeoutError("Telegram timeout"))

        with pytest.raises(OCRServerError, match="File download failed"):
            await ocr.process_passport("file_abc")

    async def test_gemini_error_through_process_card(
        self, ocr: OCRService, mock_gemini: AsyncMock, patch_to_thread,
    ):
        """Gemini API error → OCRServerError propagates from process_card."""
        mock_gemini.process_card.side_effect = genai_errors.APIError(
            500, {"error": {"message": "Internal server error"}},
        )

        with pytest.raises(OCRServerError, match="Internal server error"):
            await ocr.process_card("file_abc")
