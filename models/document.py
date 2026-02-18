from datetime import datetime

from pydantic import BaseModel


class Document(BaseModel):
    id: int
    user_id: int
    manager_id: int
    passport_file_id: str | None = None
    receipt_file_id: str | None = None
    receipt_price: int | None = None
    card_file_id: str | None = None
    card_number: str | None = None
    card_holder_name: str | None = None
    created_at: datetime
