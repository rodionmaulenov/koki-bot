import json
import logging
from typing import Any

from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig, HttpOptions, HttpRetryOptions

from models.ocr import CardResult, PassportResult, ReceiptResult
from models.video_result import VideoResult

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.5-flash"

_PASSPORT_PROMPT = (
    "Посмотри на изображение и определи: это паспорт (ID-карта с персональными данными)?\n\n"
    "Если это НЕ паспорт (чек, карта, случайное фото) — верни is_document=false, остальные поля null.\n\n"
    "Если это паспорт — извлеки ФИО и дату рождения:\n"
    "- is_document: true\n"
    "- last_name: фамилия (латиницей, как в паспорте)\n"
    "- first_name: имя (латиницей)\n"
    "- patronymic: отчество (латиницей, null если нет)\n"
    "- birth_date: дата рождения в формате DD.MM.YYYY (null если не читается)\n"
    "- Только латиница для имён, первая буква заглавная\n"
    "- Если поле не читается — null"
)

_RECEIPT_PROMPT = (
    "Посмотри на изображение и определи: это чек из аптеки?\n\n"
    "Если это НЕ чек (паспорт, карта, случайное фото) — верни is_document=false, остальные поля дефолтные.\n\n"
    "Если это чек — проверь есть ли в нём препарат (КОК — комбинированные оральные контрацептивы):\n"
    "Ищи: Регулон, Линдинет, Мерсилон, Новинет, Жанин, Ярина, Диане-35, "
    "Марвелон, Три-мерси, Логест, Фемоден, Силест, Минизистон, "
    "контрацептив, КОК, oral contraceptive, противозачаточные.\n\n"
    "- is_document: true\n"
    "- has_kok: true если нашёл препарат, false если нет\n"
    "- price: цена препарата в узбекских сумах (целое число), null если не найдена"
)

_CARD_PROMPT = (
    "Посмотри на изображение и определи: это банковская карта?\n\n"
    "Если это НЕ банковская карта (паспорт, чек, случайное фото) — верни is_document=false, остальные поля null.\n\n"
    "Если это банковская карта — извлеки данные:\n"
    "- is_document: true\n"
    "- card_number: номер карты (только 16 цифр, без пробелов)\n"
    "- card_holder: имя владельца (латиницей, как на карте)\n"
    "- Если поле не читается — null"
)

_VIDEO_PROMPT = (
    "Посмотри видео и определи: девушка принимает таблетку (КОК — оральный контрацептив)?\n\n"
    "Проверь:\n"
    "1. Человек в кадре (лицо видно)\n"
    "2. Видна таблетка, блистер или упаковка с таблетками (в руке, во рту, на столе)\n"
    "3. Действие приёма: кладёт таблетку в рот и глотает (таблетка может быть взята из блистера напрямую в рот)\n"
    "4. Видео снято вживую (не с экрана телефона/компьютера)\n\n"
    "- approved: true если все 4 пункта выполнены, false если хотя бы один нет\n"
    "- confidence: от 0.0 до 1.0, насколько ты уверен в оценке\n"
    "- reason: короткое объяснение на русском (1 предложение)"
)

_VIDEO_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["approved", "confidence", "reason"],
}

_PASSPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_document": {"type": "boolean"},
        "last_name": {"type": "string", "nullable": True},
        "first_name": {"type": "string", "nullable": True},
        "patronymic": {"type": "string", "nullable": True},
        "birth_date": {"type": "string", "nullable": True},
    },
    "required": ["is_document", "last_name", "first_name", "patronymic", "birth_date"],
}

_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "is_document": {"type": "boolean"},
        "card_number": {"type": "string", "nullable": True},
        "card_holder": {"type": "string", "nullable": True},
    },
    "required": ["is_document", "card_number", "card_holder"],
}

_RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_document": {"type": "boolean"},
        "has_kok": {"type": "boolean"},
        "price": {"type": "integer", "nullable": True},
    },
    "required": ["is_document", "has_kok", "price"],
}


class GeminiService:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if not self._api_key:
                raise ValueError("Gemini API key is not configured")
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=HttpOptions(
                    timeout=30_000,
                    retry_options=HttpRetryOptions(
                        attempts=5,
                        initial_delay=1.0,
                    ),
                ),
            )
        return self._client

    async def process_passport(self, image_bytes: bytes) -> PassportResult:
        """Classify image and extract passport fields.

        Raises on Gemini API errors (caller handles).
        """
        data = await self._generate_vision(image_bytes, _PASSPORT_PROMPT, _PASSPORT_SCHEMA)

        logger.debug("Gemini process_passport result: %s", data)
        return PassportResult(
            is_document=data.get("is_document", False),
            last_name=data.get("last_name"),
            first_name=data.get("first_name"),
            patronymic=data.get("patronymic"),
            birth_date=data.get("birth_date"),
        )

    async def process_card(self, image_bytes: bytes) -> CardResult:
        """Classify image and extract card fields.

        Raises on Gemini API errors (caller handles).
        """
        data = await self._generate_vision(image_bytes, _CARD_PROMPT, _CARD_SCHEMA)

        logger.debug("Gemini process_card result: %s", data)
        return CardResult(
            is_document=data.get("is_document", False),
            card_number=data.get("card_number"),
            card_holder=data.get("card_holder"),
        )

    async def process_receipt(self, image_bytes: bytes) -> ReceiptResult:
        """Classify image and extract receipt fields.

        Raises on Gemini API errors (caller handles).
        """
        data = await self._generate_vision(image_bytes, _RECEIPT_PROMPT, _RECEIPT_SCHEMA)

        logger.debug("Gemini process_receipt result: %s", data)
        return ReceiptResult(
            is_document=data.get("is_document", False),
            has_kok=data.get("has_kok", False),
            price=data.get("price"),
        )

    async def process_video(self, video_bytes: bytes, mime_type: str) -> VideoResult:
        """Analyze video and determine if girl is taking a pill.

        Raises on Gemini API errors (caller handles).
        """
        client = self._get_client()
        response = await client.aio.models.generate_content(
            model=_MODEL,
            contents=[
                types.Part.from_bytes(data=video_bytes, mime_type=mime_type),
                _VIDEO_PROMPT,
            ],
            config=GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_VIDEO_SCHEMA,
                temperature=0.0,
            ),
        )

        if response.text is None:
            logger.error("Gemini returned empty response for video")
            raise ValueError("Gemini returned empty response for video")

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            logger.error("Gemini video returned malformed JSON: %.200s", response.text)
            raise

        logger.debug("Gemini process_video result: %s", data)
        return VideoResult(
            approved=data.get("approved", False),
            confidence=float(data.get("confidence", 0.0)),
            reason=data.get("reason", ""),
        )

    async def _generate_vision(
        self,
        image_bytes: bytes,
        prompt: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Send image + prompt to Gemini Vision, return structured JSON."""
        client = self._get_client()
        response = await client.aio.models.generate_content(
            model=_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config=GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.0,
            ),
        )

        if response.text is None:
            logger.error("Gemini returned empty response")
            raise ValueError("Gemini returned empty response")

        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            logger.error("Gemini returned malformed JSON: %.200s", response.text)
            raise
