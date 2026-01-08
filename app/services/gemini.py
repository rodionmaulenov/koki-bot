"""Сервис проверки видео через Gemini."""

import json
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from aiogram import Bot
from google import genai
from google.genai import types

from app.config import get_settings
from app.utils.logger import log_gemini_call, log_gemini_result, log_error

settings = get_settings()

# Папка для временных файлов
TEMP_DIR = Path(__file__).parent.parent.parent / "temp"

# Промпт для проверки видео
VIDEO_VERIFICATION_PROMPT = """Analyze this short video. Determine if the person is taking a pill/medication.

Look for these signs:
1. Person puts something small (pill/tablet) in their mouth
2. Person drinks water or swallows
3. The action looks like taking oral medication

Respond in JSON format ONLY, no other text:
{
    "is_taking_pill": true or false,
    "confidence": 0-100,
    "reason": "brief explanation in Russian"
}

Scoring guide:
- 80-100: Clearly visible pill-taking action
- 60-79: Action visible but somewhat unclear
- 40-59: Hard to tell, video quality issues
- 0-39: Does not show pill-taking

Be fair but strict. This is medical compliance verification."""


class GeminiService:
    """Проверяет видео-кружочки на приём таблетки."""

    CONFIDENCE_THRESHOLD = 70

    def __init__(self, api_key: str = None, model: str = "gemini-2.0-flash"):
        self.client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self.model_name = model

    @staticmethod
    @asynccontextmanager
    async def download_video(bot: Bot, file_id: str):
        """Скачивает video_note и удаляет после использования."""
        TEMP_DIR.mkdir(exist_ok=True)
        video_path = TEMP_DIR / f"{file_id}.mp4"

        try:
            file = await bot.get_file(file_id)
            await bot.download_file(file.file_path, str(video_path))
            yield str(video_path)
        finally:
            if video_path.exists():
                video_path.unlink()

    async def verify_video(self, video_path: str) -> dict:
        """Проверяет видео и возвращает результат.

        Returns:
            {
                "is_taking_pill": bool,
                "confidence": int (0-100),
                "reason": str,
                "status": "confirmed" | "pending"
            }
        """
        try:
            log_gemini_call("verify_video", video_path)

            if not Path(video_path).exists():
                raise FileNotFoundError(f"Video not found: {video_path}")

            # Загружаем видео в Gemini
            video_file = await asyncio.to_thread(
                self.client.files.upload,
                file=video_path,
            )

            try:
                # Ждём обработки
                video_file = await self._wait_for_processing(video_file)

                # Отправляем запрос
                config = types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                )

                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=[video_file, VIDEO_VERIFICATION_PROMPT],
                    config=config,
                )

                # Парсим ответ
                result = self._parse_response(response.text)
                result["status"] = self._determine_status(
                    result["is_taking_pill"],
                    result["confidence"],
                )

                log_gemini_result(
                    result["is_taking_pill"],
                    result["confidence"],
                    result["status"],
                )

                return result

            finally:
                # Удаляем файл из Gemini
                try:
                    await asyncio.to_thread(
                        self.client.files.delete,
                        name=video_file.name,
                    )
                except Exception as e:
                    log_error(f"Failed to delete Gemini file: {e}")

        except Exception as e:
            log_error(f"Video verification error: {e}")
            return {
                "is_taking_pill": False,
                "confidence": 0,
                "reason": f"Ошибка проверки: {str(e)}",
                "status": "pending",
            }

    async def _wait_for_processing(self, video_file, timeout: int = 30):
        """Ждёт пока Gemini обработает файл."""
        attempts = 0

        while video_file.state.name == "PROCESSING":
            if attempts >= timeout:
                raise TimeoutError("Video processing timeout")

            await asyncio.sleep(1)
            video_file = await asyncio.to_thread(
                self.client.files.get,
                name=video_file.name,
            )
            attempts += 1

        if video_file.state.name == "FAILED":
            raise RuntimeError("Video processing failed")

        return video_file

    @staticmethod
    def _parse_response(response_text: str) -> dict:
        """Парсит JSON ответ от Gemini."""
        try:
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]

            result = json.loads(text.strip())

            return {
                "is_taking_pill": bool(result.get("is_taking_pill", False)),
                "confidence": int(result.get("confidence", 0)),
                "reason": str(result.get("reason", "")),
            }

        except (json.JSONDecodeError, ValueError) as e:
            log_error(f"Failed to parse Gemini response: {e}")
            return {
                "is_taking_pill": False,
                "confidence": 0,
                "reason": "Не удалось распознать ответ",
            }

    def _determine_status(self, is_taking_pill: bool, confidence: int) -> str:
        """confirmed — автоподтверждение, pending — на проверку менеджеру."""
        if is_taking_pill and confidence >= self.CONFIDENCE_THRESHOLD:
            return "confirmed"
        return "pending"