from dataclasses import dataclass

from models.enums import ReissueCategory


@dataclass(frozen=True, slots=True)
class ReissueGirl:
    course_id: int
    short_name: str
    date_str: str
    category: ReissueCategory
