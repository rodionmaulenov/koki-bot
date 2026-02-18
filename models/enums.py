from enum import StrEnum


class CourseStatus(StrEnum):
    SETUP = "setup"
    ACTIVE = "active"
    COMPLETED = "completed"
    REFUSED = "refused"
    EXPIRED = "expired"
    APPEAL = "appeal"


class RemovalReason:
    NO_VIDEO = "no_video"
    MAX_STRIKES = "max_strikes"
    MANAGER_REJECT = "manager_reject"
    REVIEW_DEADLINE = "review_deadline"
    RESHOOT_EXPIRED = "reshoot_expired"
    APPEAL_DECLINED = "appeal_declined"
    APPEAL_EXPIRED = "appeal_expired"

    APPEALABLE = (NO_VIDEO, MAX_STRIKES)


class ReissueCategory(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    EXPIRED = "expired"
