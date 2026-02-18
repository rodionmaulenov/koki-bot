from datetime import date, datetime, time

from pydantic import BaseModel

from models.enums import CourseStatus


class Course(BaseModel):
    id: int
    user_id: int
    status: CourseStatus
    invite_code: str | None = None
    invite_used: bool = False
    cycle_day: int | None = None
    intake_time: time | None = None
    start_date: date | None = None
    current_day: int = 0
    late_count: int = 0
    total_days: int = 21
    registration_message_id: int | None = None
    extended: bool = False
    appeal_count: int = 0
    appeal_video: str | None = None
    appeal_text: str | None = None
    removal_reason: str | None = None
    late_dates: list[str] = []
    created_at: datetime
    updated_at: datetime | None = None
