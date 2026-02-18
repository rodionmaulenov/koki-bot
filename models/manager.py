from datetime import datetime

from pydantic import BaseModel

from models.enums import ManagerRole


class Manager(BaseModel):
    id: int
    telegram_id: int
    name: str
    is_active: bool
    role: ManagerRole = ManagerRole.MANAGER
    created_at: datetime
