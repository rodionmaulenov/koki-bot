from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    id: int
    telegram_id: int | None = None
    name: str
    manager_id: int
    topic_id: int | None = None
    created_at: datetime
