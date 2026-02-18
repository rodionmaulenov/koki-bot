"""Tests for GeminiService — unit tests with mocked Gemini client.

Key logic tested:
- Lazy client init with empty API key validation
- JSON → dataclass mapping for passport/card/receipt/video
- Default values when JSON fields are missing
- Error handling: None response, malformed JSON
- process_video uses caller's mime_type (not hardcoded "image/jpeg")
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.ocr import CardResult, PassportResult, ReceiptResult
from models.video_result import VideoResult
from services.gemini_service import GeminiService


# =============================================================================
# HELPERS
# =============================================================================


def _mock_response(text: str | None) -> MagicMock:
    """Simulate Gemini API response with given text."""
    response = MagicMock()
    response.text = text
    return response


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_client() -> MagicMock:
    """Mock genai.Client with async generate_content."""
    return MagicMock()


@pytest.fixture
def gemini(mock_client) -> GeminiService:
    """GeminiService with pre-injected mock client (bypasses lazy init)."""
    service = GeminiService(api_key="test-key")
    service._client = mock_client
    return service


# =============================================================================
# GET CLIENT
# =============================================================================


class TestGetClient:
    def test_empty_key_raises_value_error(self):
        service = GeminiService(api_key="")
        with pytest.raises(ValueError, match="not configured"):
            service._get_client()

    def test_returns_cached_client(self):
        service = GeminiService(api_key="test-key")
        sentinel = MagicMock()
        service._client = sentinel
        assert service._get_client() is sentinel


# =============================================================================
# VISION ERROR HANDLING (tested via process_passport)
# =============================================================================


class TestVisionErrorHandling:
    async def test_empty_response_raises_value_error(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(None),
        )

        with pytest.raises(ValueError, match="empty response"):
            await gemini.process_passport(b"fake-image")

    async def test_malformed_json_raises(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response("not valid json {{{"),
        )

        with pytest.raises(json.JSONDecodeError):
            await gemini.process_passport(b"fake-image")


# =============================================================================
# PROCESS PASSPORT
# =============================================================================


class TestProcessPassport:
    async def test_full_data(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "is_document": True,
                "last_name": "IVANOVA",
                "first_name": "MARINA",
                "patronymic": "ALEXANDROVNA",
                "birth_date": "15.06.2000",
            })),
        )

        result = await gemini.process_passport(b"fake-image")

        assert isinstance(result, PassportResult)
        assert result.is_document is True
        assert result.last_name == "IVANOVA"
        assert result.first_name == "MARINA"
        assert result.patronymic == "ALEXANDROVNA"
        assert result.birth_date == "15.06.2000"

    async def test_not_a_document(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "is_document": False,
                "last_name": None,
                "first_name": None,
                "patronymic": None,
                "birth_date": None,
            })),
        )

        result = await gemini.process_passport(b"fake-image")

        assert result.is_document is False
        assert result.last_name is None
        assert result.first_name is None

    async def test_missing_fields_defaults(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        """Empty JSON → is_document=False, all fields None."""
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response("{}"),
        )

        result = await gemini.process_passport(b"fake-image")

        assert result.is_document is False
        assert result.last_name is None
        assert result.first_name is None
        assert result.patronymic is None
        assert result.birth_date is None


# =============================================================================
# PROCESS CARD
# =============================================================================


class TestProcessCard:
    async def test_full_data(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "is_document": True,
                "card_number": "8600123456789012",
                "card_holder": "IVANOVA MARINA",
            })),
        )

        result = await gemini.process_card(b"fake-image")

        assert isinstance(result, CardResult)
        assert result.is_document is True
        assert result.card_number == "8600123456789012"
        assert result.card_holder == "IVANOVA MARINA"

    async def test_not_a_document(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "is_document": False,
                "card_number": None,
                "card_holder": None,
            })),
        )

        result = await gemini.process_card(b"fake-image")

        assert result.is_document is False
        assert result.card_number is None
        assert result.card_holder is None

    async def test_missing_fields_defaults(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response("{}"),
        )

        result = await gemini.process_card(b"fake-image")

        assert result.is_document is False
        assert result.card_number is None
        assert result.card_holder is None


# =============================================================================
# PROCESS RECEIPT
# =============================================================================


class TestProcessReceipt:
    async def test_full_data(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "is_document": True,
                "has_kok": True,
                "price": 50000,
            })),
        )

        result = await gemini.process_receipt(b"fake-image")

        assert isinstance(result, ReceiptResult)
        assert result.is_document is True
        assert result.has_kok is True
        assert result.price == 50000

    async def test_not_a_document(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "is_document": False,
                "has_kok": False,
                "price": None,
            })),
        )

        result = await gemini.process_receipt(b"fake-image")

        assert result.is_document is False
        assert result.has_kok is False
        assert result.price is None

    async def test_missing_has_kok_defaults_false(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        """has_kok missing from JSON → defaults to False (not None!)."""
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({"is_document": True})),
        )

        result = await gemini.process_receipt(b"fake-image")

        assert result.has_kok is False
        assert result.price is None


# =============================================================================
# PROCESS VIDEO
# =============================================================================


class TestProcessVideo:
    async def test_approved(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "approved": True,
                "confidence": 0.95,
                "reason": "Girl takes pill on camera",
            })),
        )

        result = await gemini.process_video(b"fake-video", "video/mp4")

        assert isinstance(result, VideoResult)
        assert result.approved is True
        assert result.confidence == 0.95
        assert result.reason == "Girl takes pill on camera"

    async def test_not_approved(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "approved": False,
                "confidence": 0.3,
                "reason": "No pill visible",
            })),
        )

        result = await gemini.process_video(b"fake-video", "video/mp4")

        assert result.approved is False
        assert result.confidence == 0.3
        assert result.reason == "No pill visible"

    async def test_confidence_cast_to_float(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        """Integer confidence from JSON → cast to float via float()."""
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "approved": True,
                "confidence": 1,
                "reason": "OK",
            })),
        )

        result = await gemini.process_video(b"fake-video", "video/mp4")

        assert result.confidence == 1.0
        assert isinstance(result.confidence, float)

    async def test_missing_fields_defaults(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        """Empty JSON → approved=False, confidence=0.0, reason=''."""
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response("{}"),
        )

        result = await gemini.process_video(b"fake-video", "video/mp4")

        assert result.approved is False
        assert result.confidence == 0.0
        assert isinstance(result.confidence, float)
        assert result.reason == ""

    async def test_empty_response_raises_value_error(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        """process_video has its OWN None check (separate from _generate_vision)."""
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(None),
        )

        with pytest.raises(ValueError, match="empty response for video"):
            await gemini.process_video(b"fake-video", "video/mp4")

    async def test_malformed_json_raises(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response("broken json!!!"),
        )

        with pytest.raises(json.JSONDecodeError):
            await gemini.process_video(b"fake-video", "video/mp4")

    async def test_mime_type_forwarded(
        self, gemini: GeminiService, mock_client: MagicMock,
    ):
        """Caller's mime_type is forwarded to API (not hardcoded 'image/jpeg')."""
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_mock_response(json.dumps({
                "approved": True, "confidence": 0.9, "reason": "OK",
            })),
        )

        await gemini.process_video(b"fake-video", "video/quicktime")

        assert mock_client.aio.models.generate_content.call_count == 1