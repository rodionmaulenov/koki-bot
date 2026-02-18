from datetime import datetime

from pydantic import BaseModel


class CommandsMessage(BaseModel):
    id: int
    message_id: int
    bot_type: str
    is_menu: bool = False
    created_at: datetime
