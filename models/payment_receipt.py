from datetime import datetime

from pydantic import BaseModel


class PaymentReceipt(BaseModel):
    id: int
    course_id: int
    accountant_id: int
    receipt_file_id: str
    amount: int | None = None
    created_at: datetime
