from pydantic import BaseModel


class WAButton(BaseModel):
    id: str
    title: str  # max 20 chars


class WASendInteractiveRequest(BaseModel):
    """Запрос на отправку interactive message с фото и кнопками."""

    to: str  # номер телефона или group ID
    image_url: str
    body_text: str
    buttons: list[WAButton]  # max 3


class WAWebhookMessage(BaseModel):
    """Parsed button_reply из webhook payload."""

    from_number: str
    button_id: str
    message_id: str
    timestamp: str
