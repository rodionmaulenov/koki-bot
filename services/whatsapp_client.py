import hashlib
import hmac
import logging
from io import BytesIO
from typing import Any

import httpx

from config import Settings

logger = logging.getLogger(__name__)

_GRAPH_API_BASE = "https://graph.facebook.com"
_TELEGRAM_API_BASE = "https://api.telegram.org"


class WhatsAppClient:
    def __init__(self, settings: Settings) -> None:
        self._phone_number_id = settings.whatsapp_phone_number_id
        self._access_token = settings.whatsapp_access_token
        self._app_secret = settings.whatsapp_app_secret
        self._verify_token = settings.whatsapp_verify_token
        self._api_version = settings.whatsapp_api_version
        self._group_id = settings.whatsapp_group_id
        self._bot_token = settings.bot_token
        self._client: httpx.AsyncClient | None = None

    @property
    def verify_token(self) -> str:
        return self._verify_token

    @property
    def group_id(self) -> str:
        return self._group_id

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=f"{_GRAPH_API_BASE}/{self._api_version}",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Проверка HMAC-SHA256 подписи из X-Hub-Signature-256."""
        if not signature.startswith("sha256="):
            return False
        expected = hmac.new(
            self._app_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    async def download_telegram_file(self, file_id: str) -> bytes:
        """Скачать файл из Telegram по file_id."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Получаем file_path
            resp = await client.get(
                f"{_TELEGRAM_API_BASE}/bot{self._bot_token}/getFile",
                params={"file_id": file_id},
            )
            resp.raise_for_status()
            file_path = resp.json()["result"]["file_path"]

            # Скачиваем файл
            resp = await client.get(
                f"{_TELEGRAM_API_BASE}/file/bot{self._bot_token}/{file_path}",
            )
            resp.raise_for_status()
            logger.info("Downloaded Telegram file_id=%s, size=%d", file_id, len(resp.content))
            return resp.content

    async def upload_media(self, file_bytes: bytes, mime_type: str) -> str:
        """Загрузить файл в Meta → вернуть media_id."""
        async with httpx.AsyncClient(
            base_url=f"{_GRAPH_API_BASE}/{self._api_version}",
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=30.0,
        ) as client:
            resp = await client.post(
                f"/{self._phone_number_id}/media",
                data={"messaging_product": "whatsapp", "type": mime_type},
                files={"file": ("photo.jpg", BytesIO(file_bytes), mime_type)},
            )
            resp.raise_for_status()
            media_id = resp.json()["id"]
            logger.info("Uploaded media to Meta, media_id=%s", media_id)
            return media_id

    async def send_image_by_media_id(
        self,
        to: str,
        media_id: str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """Отправить фото по media_id."""
        image_payload: dict[str, str] = {"id": media_id}
        if caption:
            image_payload["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": image_payload,
        }
        client = self._get_client()
        response = await client.post(
            f"/{self._phone_number_id}/messages",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        logger.info("WhatsApp image (media_id) sent to=%s, wa_id=%s", to, data)
        return data

    async def send_interactive_message(
        self,
        to: str,
        header_image_url: str,
        body_text: str,
        buttons: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Отправить сообщение с фото и кнопками (max 3, title max 20 chars)."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "image",
                    "image": {"link": header_image_url},
                },
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": btn["id"], "title": btn["title"]},
                        }
                        for btn in buttons
                    ],
                },
            },
        }
        client = self._get_client()
        response = await client.post(
            f"/{self._phone_number_id}/messages",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        logger.info("WhatsApp interactive sent to=%s, wa_id=%s", to, data)
        return data

    async def send_image(
        self,
        to: str,
        image_url: str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """Отправить фото по URL."""
        image_payload: dict[str, str] = {"link": image_url}
        if caption:
            image_payload["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": image_payload,
        }
        client = self._get_client()
        response = await client.post(
            f"/{self._phone_number_id}/messages",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        logger.info("WhatsApp image sent to=%s, wa_id=%s", to, data)
        return data

    async def mark_as_read(self, message_id: str) -> None:
        """Синие галочки (fire-and-forget)."""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        client = self._get_client()
        try:
            response = await client.post(
                f"/{self._phone_number_id}/messages",
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Failed to mark message %s as read", message_id)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
