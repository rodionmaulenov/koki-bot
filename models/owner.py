from datetime import datetime

from pydantic import BaseModel


class Owner(BaseModel):
    id: int
    telegram_id: int
    name: str
    is_active: bool
    created_at: datetime
