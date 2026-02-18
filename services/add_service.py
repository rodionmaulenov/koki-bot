import logging
import secrets
import string
from datetime import date, datetime, time as dt_time, timedelta

from supabase import AsyncClient

from models.course import Course
from models.enums import CourseStatus, ReissueCategory
from models.reissue import ReissueGirl
from models.user import User
from repositories.course_repository import CourseRepository
from repositories.user_repository import UserRepository
from utils.time import TASHKENT_TZ, get_tashkent_now

logger = logging.getLogger(__name__)

_CODE_LENGTH = 12
_CODE_ALPHABET = string.ascii_letters + string.digits
_REISSUE_CUTOFF_DAYS = 7
_PATRONYMIC_SUFFIXES = frozenset({"kizi", "qizi"})

_CATEGORY_ORDER: dict[ReissueCategory, int] = {
    ReissueCategory.NOT_STARTED: 0,
    ReissueCategory.IN_PROGRESS: 1,
    ReissueCategory.EXPIRED: 2,
}


def _generate_invite_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def abbreviate_name(full_name: str) -> str:
    """Abbreviate 'Ivanova Marina Alexandrovna kizi' → 'Ivanova M.A.'"""
    parts = full_name.split()
    if not parts:
        return full_name

    last_name = parts[0]
    initials = ""
    for part in parts[1:]:
        if part.lower() in _PATRONYMIC_SUFFIXES:
            continue
        if part:
            initials += part[0].upper() + "."

    if initials:
        return f"{last_name} {initials}"
    return last_name


def _classify_course(
    course_date: date, user: User, today: date,
) -> ReissueCategory:
    """Determine reissue category based on course date and user state."""
    if course_date < today:
        return ReissueCategory.EXPIRED
    if user.telegram_id is not None:
        return ReissueCategory.IN_PROGRESS
    return ReissueCategory.NOT_STARTED


class AddService:
    def __init__(
        self,
        supabase: AsyncClient,
        user_repository: UserRepository,
        course_repository: CourseRepository,
    ) -> None:
        self._supabase = supabase
        self._user_repository = user_repository
        self._course_repository = course_repository

    async def create_link(
        self,
        manager_id: int,
        name: str,
        passport_file_id: str,
        receipt_file_id: str,
        receipt_price: int,
        card_file_id: str,
        card_number: str,
        card_holder_name: str,
        birth_date: str | None = None,
        existing_user_id: int | None = None,
    ) -> Course:
        invite_code = _generate_invite_code()

        params: dict = {
            "p_name": name,
            "p_manager_id": manager_id,
            "p_passport_file_id": passport_file_id,
            "p_receipt_file_id": receipt_file_id,
            "p_receipt_price": receipt_price,
            "p_card_file_id": card_file_id,
            "p_card_number": card_number,
            "p_card_holder_name": card_holder_name,
            "p_invite_code": invite_code,
        }

        if birth_date:
            params["p_birth_date"] = birth_date
        if existing_user_id:
            params["p_existing_user_id"] = existing_user_id

        response = await self._supabase.rpc(
            "create_user_with_documents", params,
        ).execute()

        return Course(**response.data)

    async def get_reissuable_girls(
        self, manager_id: int,
    ) -> list[ReissueGirl]:
        users = await self._user_repository.get_by_manager_id(manager_id)
        if not users:
            return []

        user_ids = [u.id for u in users]
        today = get_tashkent_now().date()
        cutoff_dt = datetime.combine(
            today - timedelta(days=_REISSUE_CUTOFF_DAYS),
            dt_time.min,
            tzinfo=TASHKENT_TZ,
        )

        courses = await self._course_repository.get_reissuable_by_user_ids(
            user_ids, cutoff=cutoff_dt,
        )
        if not courses:
            return []

        user_map: dict[int, User] = {u.id: u for u in users}
        seen_user_ids: set[int] = set()
        result: list[ReissueGirl] = []
        expired_course_ids: list[int] = []

        for course in courses:
            if course.user_id in seen_user_ids:
                continue
            seen_user_ids.add(course.user_id)

            user = user_map.get(course.user_id)
            if user is None:
                logger.warning(
                    "User not found for course: course_id=%d, user_id=%d",
                    course.id, course.user_id,
                )
                continue

            course_date = course.created_at.astimezone(TASHKENT_TZ).date()
            category = _classify_course(course_date, user, today)

            if category == ReissueCategory.EXPIRED and course.status == CourseStatus.SETUP:
                expired_course_ids.append(course.id)

            result.append(ReissueGirl(
                course_id=course.id,
                short_name=abbreviate_name(user.name),
                date_str=course_date.strftime("%d.%m"),
                category=category,
            ))

        if expired_course_ids:
            try:
                await self._course_repository.set_expired_batch(expired_course_ids)
            except Exception:
                logger.exception(
                    "Failed to set_expired_batch: course_ids=%s",
                    expired_course_ids,
                )

        result.sort(key=lambda g: _CATEGORY_ORDER[g.category])
        return result

    async def reissue_link(self, course_id: int) -> Course:
        invite_code = _generate_invite_code()
        return await self._course_repository.reissue(course_id, invite_code)
