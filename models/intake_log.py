from datetime import datetime

from pydantic import BaseModel


class IntakeLog(BaseModel):
    id: int
    course_id: int
    day: int
    scheduled_at: datetime | None = None
    taken_at: datetime | None = None
    status: str = "pending"
    delay_minutes: int | None = None
    video_file_id: str | None = None
    verified_by: str | None = None
    confidence: float | None = None
    review_started_at: datetime | None = None
    reshoot_deadline: datetime | None = None
    private_message_id: int | None = None
    created_at: datetime
