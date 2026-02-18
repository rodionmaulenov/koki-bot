import json
import logging

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Request, Response

from services.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)

router = APIRouter(route_class=DishkaRoute)


@router.get("/webhook")
async def verify_webhook(
    request: Request,
    wa_client: FromDishka[WhatsAppClient],
) -> Response:
    """Meta webhook верификация (challenge-response)."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == wa_client.verify_token:
        logger.info("Webhook verified")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Webhook verification failed: mode=%s", mode)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    wa_client: FromDishka[WhatsAppClient],
) -> dict:
    """Приём событий от Meta (нажатия кнопок)."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not wa_client.verify_signature(body, signature):
        logger.warning(
            "Invalid webhook signature from %s",
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = json.loads(body)

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for msg in value.get("messages", []):
                if msg.get("type") != "interactive":
                    continue

                interactive = msg.get("interactive", {})
                if interactive.get("type") != "button_reply":
                    continue

                button_id = interactive.get("button_reply", {}).get("id", "")
                from_number = msg.get("from", "")
                message_id = msg.get("id", "")

                if not from_number or not button_id:
                    logger.warning("Webhook missing from_number or button_id")
                    continue

                logger.info(
                    "Button click: from=%s, button_id=%s, msg_id=%s",
                    from_number, button_id, message_id,
                )

                await wa_client.mark_as_read(message_id)
                await _handle_button_click(wa_client, button_id)

    return {"status": "ok"}


async def _handle_button_click(wa_client: WhatsAppClient, button_id: str) -> None:
    """Парсим button_id, скачиваем из Telegram, отправляем в группу."""
    if ":" not in button_id:
        logger.warning("Unknown button_id format: %s", button_id)
        return

    doc_type, file_id = button_id.split(":", maxsplit=1)

    if doc_type not in ("passport", "card"):
        logger.warning("Unknown doc_type in button_id: %s", doc_type)
        return

    if not file_id:
        logger.warning("Empty file_id in button_id: %s", button_id)
        return

    group_id = wa_client.group_id
    if not group_id:
        logger.error("WHATSAPP_GROUP_ID not configured")
        return

    try:
        file_bytes = await wa_client.download_telegram_file(file_id)
    except Exception:
        logger.exception("Failed to download Telegram file_id=%s", file_id)
        return

    try:
        media_id = await wa_client.upload_media(file_bytes, "image/jpeg")
    except Exception:
        logger.exception("Failed to upload media to Meta for file_id=%s", file_id)
        return

    caption = "Паспорт" if doc_type == "passport" else "Карта"

    try:
        await wa_client.send_image_by_media_id(to=group_id, media_id=media_id, caption=caption)
        logger.info("Sent %s photo to group=%s", doc_type, group_id)
    except Exception:
        logger.exception("Failed to send image to group=%s", group_id)