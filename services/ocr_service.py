import asyncio
import io
import json
import logging

from aiogram import Bot
from google.genai import errors as genai_errors

from models.ocr import (
    CardResult,
    OCRServerError,
    PassportResult,
    PaymentReceiptResult,
    ReceiptResult,
)
from services.gemini_service import GeminiService
from utils.image import preprocess_image

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(self, gemini: GeminiService, bot: Bot) -> None:
        self._gemini = gemini
        self._bot = bot

    async def process_passport(self, file_id: str) -> PassportResult | None:
        """Full passport pipeline: download → preprocess → Gemini Vision.

        Returns PassportResult (check is_document for classification).
        Returns None on unexpected empty response.
        Raises OCRServerError on API/server errors.
        """
        image_bytes = await self._download_and_preprocess(file_id)
        return await self._call_gemini(
            self._gemini.process_passport, image_bytes, "passport", file_id,
        )

    async def process_receipt(self, file_id: str) -> ReceiptResult | None:
        """Full receipt pipeline: download → preprocess → Gemini Vision.

        Returns ReceiptResult (check is_document for classification).
        Returns None on unexpected empty response.
        Raises OCRServerError on API/server errors.
        """
        image_bytes = await self._download_and_preprocess(file_id)
        return await self._call_gemini(
            self._gemini.process_receipt, image_bytes, "receipt", file_id,
        )

    async def process_card(self, file_id: str) -> CardResult | None:
        """Full card pipeline: download → preprocess → Gemini Vision.

        Returns CardResult (check is_document for classification).
        Returns None on unexpected empty response.
        Raises OCRServerError on API/server errors.
        """
        image_bytes = await self._download_and_preprocess(file_id)
        return await self._call_gemini(
            self._gemini.process_card, image_bytes, "card", file_id,
        )

    async def process_payment_receipt(self, file_id: str) -> PaymentReceiptResult | None:
        """Full payment receipt pipeline: download → preprocess → Gemini Vision.

        Returns PaymentReceiptResult (check is_document for classification).
        Returns None on unexpected empty response.
        Raises OCRServerError on API/server errors.
        """
        image_bytes = await self._download_and_preprocess(file_id)
        return await self._call_gemini(
            self._gemini.process_payment_receipt, image_bytes, "payment_receipt", file_id,
        )

    async def _download_and_preprocess(self, file_id: str) -> bytes:
        """Download file from Telegram and preprocess for OCR."""
        try:
            buffer = io.BytesIO()
            await self._bot.download(file_id, destination=buffer)
            image_bytes = buffer.getvalue()
        except Exception as e:
            logger.error("Failed to download file_id=%s: %s", file_id, e)
            raise OCRServerError(f"File download failed: {e}") from e

        return await asyncio.to_thread(preprocess_image, image_bytes)

    async def _call_gemini(self, method, image_bytes: bytes, doc_type: str, file_id: str):
        """Call a Gemini processing method with standard error handling."""
        try:
            return await method(image_bytes)
        except genai_errors.APIError as e:
            logger.error(
                "OCR %s Gemini API error [%s]: %s, file_id=%s",
                doc_type, e.code, e.message, file_id,
            )
            raise OCRServerError(str(e.message)) from e
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(
                "OCR %s Gemini bad response, file_id=%s: %s",
                doc_type, file_id, e,
            )
            raise OCRServerError(str(e)) from e
