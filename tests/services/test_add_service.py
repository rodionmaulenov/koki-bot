"""Tests for AddService — unit tests with mocked dependencies.

Key logic tested:
- Invite code generation (length, alphabet, uniqueness)
- Name abbreviation with Uzbek patronymic suffixes (kizi/qizi)
- Course classification for reissue (EXPIRED/IN_PROGRESS/NOT_STARTED)
- Reissuable girls: dedup, sort, batch expiry, error handling
"""
import string
from datetime import date, datetime, time as dt_time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.course import Course
from models.enums import CourseStatus, ReissueCategory
from models.user import User
from services.add_service import (
    AddService,
    _classify_course,
    _generate_invite_code,
    abbreviate_name,
)
from utils.time import TASHKENT_TZ


# =============================================================================
# HELPERS
# =============================================================================


def make_user(**overrides) -> User:
    defaults = {
        "id": 1,
        "name": "Ivanova Marina",
        "manager_id": 1,
        "created_at": datetime(2026, 1, 1, tzinfo=TASHKENT_TZ),
    }
    defaults.update(overrides)
    return User(**defaults)


def make_course(**overrides) -> Course:
    defaults = {
        "id": 1,
        "user_id": 1,
        "status": CourseStatus.SETUP,
        "current_day": 0,
        "total_days": 21,
        "late_count": 0,
        "appeal_count": 0,
        "late_dates": [],
        "created_at": datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ),
    }
    defaults.update(overrides)
    return Course(**defaults)


def _course_response_data(**overrides) -> dict:
    """Dict that Course(**data) can parse — simulates RPC response."""
    defaults = {
        "id": 1,
        "user_id": 1,
        "status": "setup",
        "invite_code": "TESTCODE1234",
        "invite_used": False,
        "current_day": 0,
        "total_days": 21,
        "late_count": 0,
        "appeal_count": 0,
        "late_dates": [],
        "created_at": "2026-06-15T10:00:00+05:00",
    }
    defaults.update(overrides)
    return defaults


# =============================================================================
# LOCAL FIXTURES (shadow conftest for add_service-specific patches)
# =============================================================================


@pytest.fixture
def frozen_now():
    """Patch get_tashkent_now() in add_service module."""
    with patch("services.add_service.get_tashkent_now") as mock:
        yield mock


@pytest.fixture
def fixed_code():
    """Patch _generate_invite_code() to return deterministic code."""
    with patch(
        "services.add_service._generate_invite_code",
        return_value="FIXEDCODE123",
    ) as mock:
        yield mock


# =============================================================================
# GENERATE INVITE CODE
# =============================================================================


class TestGenerateInviteCode:
    def test_length_is_12(self):
        code = _generate_invite_code()
        assert len(code) == 12

    def test_characters_from_alphabet(self):
        code = _generate_invite_code()
        allowed = set(string.ascii_letters + string.digits)
        assert all(c in allowed for c in code)

    def test_different_each_call(self):
        codes = {_generate_invite_code() for _ in range(10)}
        assert len(codes) > 1


# =============================================================================
# ABBREVIATE NAME
# =============================================================================


class TestAbbreviateName:
    def test_empty_string(self):
        assert abbreviate_name("") == ""

    def test_single_word(self):
        assert abbreviate_name("Ivanova") == "Ivanova"

    def test_two_words(self):
        assert abbreviate_name("Ivanova Marina") == "Ivanova M."

    def test_three_words(self):
        assert abbreviate_name("Ivanova Marina Alexandrovna") == "Ivanova M.A."

    def test_skips_kizi(self):
        assert abbreviate_name("Ivanova Marina kizi") == "Ivanova M."

    def test_skips_qizi(self):
        assert abbreviate_name("Ivanova Marina Alexandrovna qizi") == "Ivanova M.A."

    def test_case_insensitive_suffix(self):
        assert abbreviate_name("Ivanova Marina KIZI") == "Ivanova M."

    def test_only_suffix_no_initials(self):
        """Last name + only patronymic suffix → no initials, just last name."""
        assert abbreviate_name("Ivanova kizi") == "Ivanova"


# =============================================================================
# CLASSIFY COURSE
# =============================================================================


class TestClassifyCourse:
    def test_past_date_is_expired(self):
        today = date(2026, 6, 15)
        user = make_user(telegram_id=None)
        assert _classify_course(date(2026, 6, 14), user, today) == ReissueCategory.EXPIRED

    def test_today_with_telegram_is_in_progress(self):
        today = date(2026, 6, 15)
        user = make_user(telegram_id=123)
        assert _classify_course(today, user, today) == ReissueCategory.IN_PROGRESS

    def test_today_without_telegram_is_not_started(self):
        today = date(2026, 6, 15)
        user = make_user(telegram_id=None)
        assert _classify_course(today, user, today) == ReissueCategory.NOT_STARTED

    def test_expired_ignores_telegram_id(self):
        """Past date → EXPIRED even if user has telegram_id (first check wins)."""
        today = date(2026, 6, 15)
        user = make_user(telegram_id=123)
        assert _classify_course(date(2026, 6, 14), user, today) == ReissueCategory.EXPIRED


# =============================================================================
# CREATE LINK
# =============================================================================


class TestCreateLink:
    async def test_calls_rpc_with_all_params(
        self,
        add_service: AddService,
        mock_supabase: MagicMock,
        fixed_code,
    ):
        """All required params passed to RPC, optional absent."""
        mock_supabase.rpc.return_value.execute = AsyncMock(
            return_value=MagicMock(data=_course_response_data()),
        )

        result = await add_service.create_link(
            manager_id=5,
            name="Ivanova Marina",
            passport_file_id="pass_1",
            receipt_file_id="rcpt_1",
            receipt_price=50000,
            card_file_id="card_1",
            card_number="8600123456789012",
            card_holder_name="IVANOVA MARINA",
        )

        mock_supabase.rpc.assert_called_once()
        call_args = mock_supabase.rpc.call_args
        assert call_args[0][0] == "create_user_with_documents"
        params = call_args[0][1]
        assert params["p_manager_id"] == 5
        assert params["p_name"] == "Ivanova Marina"
        assert params["p_invite_code"] == "FIXEDCODE123"
        assert params["p_passport_file_id"] == "pass_1"
        assert params["p_receipt_price"] == 50000
        assert "p_birth_date" not in params
        assert "p_existing_user_id" not in params
        assert isinstance(result, Course)

    async def test_includes_birth_date(
        self,
        add_service: AddService,
        mock_supabase: MagicMock,
        fixed_code,
    ):
        mock_supabase.rpc.return_value.execute = AsyncMock(
            return_value=MagicMock(data=_course_response_data()),
        )

        await add_service.create_link(
            manager_id=5, name="Test", passport_file_id="p",
            receipt_file_id="r", receipt_price=1, card_file_id="c",
            card_number="1234", card_holder_name="T",
            birth_date="15.06.2000",
        )

        params = mock_supabase.rpc.call_args[0][1]
        assert params["p_birth_date"] == "15.06.2000"

    async def test_includes_existing_user_id(
        self,
        add_service: AddService,
        mock_supabase: MagicMock,
        fixed_code,
    ):
        mock_supabase.rpc.return_value.execute = AsyncMock(
            return_value=MagicMock(data=_course_response_data()),
        )

        await add_service.create_link(
            manager_id=5, name="Test", passport_file_id="p",
            receipt_file_id="r", receipt_price=1, card_file_id="c",
            card_number="1234", card_holder_name="T",
            existing_user_id=42,
        )

        params = mock_supabase.rpc.call_args[0][1]
        assert params["p_existing_user_id"] == 42


# =============================================================================
# GET REISSUABLE GIRLS
# =============================================================================


class TestGetReissuableGirls:
    async def test_no_users_returns_empty(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
    ):
        mock_user_repo.get_by_manager_id.return_value = []

        result = await add_service.get_reissuable_girls(manager_id=1)

        assert result == []
        mock_user_repo.get_by_manager_id.assert_called_once_with(1)

    async def test_no_courses_returns_empty(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)
        mock_user_repo.get_by_manager_id.return_value = [make_user(id=1)]
        mock_course_repo.get_reissuable_by_user_ids.return_value = []

        result = await add_service.get_reissuable_girls(manager_id=1)

        assert result == []

    async def test_sorted_by_category(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """Result sorted: NOT_STARTED → IN_PROGRESS → EXPIRED."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)

        users = [
            make_user(id=1, name="Aaa Bbb", telegram_id=None),
            make_user(id=2, name="Ccc Ddd", telegram_id=123),
            make_user(id=3, name="Eee Fff", telegram_id=None),
        ]
        mock_user_repo.get_by_manager_id.return_value = users

        courses = [
            make_course(id=10, user_id=3, created_at=datetime(2026, 6, 13, 10, 0, tzinfo=TASHKENT_TZ)),  # EXPIRED
            make_course(id=11, user_id=2, created_at=datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)),  # IN_PROGRESS
            make_course(id=12, user_id=1, created_at=datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)),  # NOT_STARTED
        ]
        mock_course_repo.get_reissuable_by_user_ids.return_value = courses

        result = await add_service.get_reissuable_girls(manager_id=1)

        assert len(result) == 3
        assert result[0].category == ReissueCategory.NOT_STARTED
        assert result[1].category == ReissueCategory.IN_PROGRESS
        assert result[2].category == ReissueCategory.EXPIRED

    async def test_deduplicates_by_user_id(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """Two courses for same user → only first kept."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)

        mock_user_repo.get_by_manager_id.return_value = [make_user(id=1)]
        mock_course_repo.get_reissuable_by_user_ids.return_value = [
            make_course(id=10, user_id=1),
            make_course(id=11, user_id=1),
        ]

        result = await add_service.get_reissuable_girls(manager_id=1)

        assert len(result) == 1
        assert result[0].course_id == 10

    async def test_skips_missing_user(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """Course with user_id not in users list → skipped."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)

        mock_user_repo.get_by_manager_id.return_value = [make_user(id=1)]
        mock_course_repo.get_reissuable_by_user_ids.return_value = [
            make_course(id=10, user_id=999),  # user not in list
        ]

        result = await add_service.get_reissuable_girls(manager_id=1)

        assert result == []

    async def test_expired_setup_calls_set_expired(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """EXPIRED + SETUP course → set_expired_batch called."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)

        mock_user_repo.get_by_manager_id.return_value = [
            make_user(id=1, telegram_id=None),
        ]
        mock_course_repo.get_reissuable_by_user_ids.return_value = [
            make_course(
                id=10, user_id=1, status=CourseStatus.SETUP,
                created_at=datetime(2026, 6, 13, 10, 0, tzinfo=TASHKENT_TZ),
            ),
        ]

        await add_service.get_reissuable_girls(manager_id=1)

        mock_course_repo.set_expired_batch.assert_called_once_with([10])

    async def test_expired_active_not_batch_expired(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """EXPIRED + ACTIVE → set_expired_batch NOT called (only SETUP gets expired)."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)

        mock_user_repo.get_by_manager_id.return_value = [
            make_user(id=1, telegram_id=None),
        ]
        mock_course_repo.get_reissuable_by_user_ids.return_value = [
            make_course(
                id=10, user_id=1, status=CourseStatus.ACTIVE,
                created_at=datetime(2026, 6, 13, 10, 0, tzinfo=TASHKENT_TZ),
            ),
        ]

        await add_service.get_reissuable_girls(manager_id=1)

        mock_course_repo.set_expired_batch.assert_not_called()

    async def test_set_expired_exception_caught(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """set_expired_batch raises → exception caught, result still returned."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)

        mock_user_repo.get_by_manager_id.return_value = [
            make_user(id=1, telegram_id=None),
        ]
        mock_course_repo.get_reissuable_by_user_ids.return_value = [
            make_course(
                id=10, user_id=1, status=CourseStatus.SETUP,
                created_at=datetime(2026, 6, 13, 10, 0, tzinfo=TASHKENT_TZ),
            ),
        ]
        mock_course_repo.set_expired_batch.side_effect = RuntimeError("DB error")

        result = await add_service.get_reissuable_girls(manager_id=1)

        assert len(result) == 1
        assert result[0].category == ReissueCategory.EXPIRED

    async def test_date_str_format(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """date_str is formatted as DD.MM."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)

        mock_user_repo.get_by_manager_id.return_value = [
            make_user(id=1, telegram_id=None),
        ]
        mock_course_repo.get_reissuable_by_user_ids.return_value = [
            make_course(
                id=10, user_id=1,
                created_at=datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ),
            ),
        ]

        result = await add_service.get_reissuable_girls(manager_id=1)

        assert result[0].date_str == "15.06"

    async def test_cutoff_is_7_days_ago(
        self,
        add_service: AddService,
        mock_user_repo: AsyncMock,
        mock_course_repo: AsyncMock,
        frozen_now,
    ):
        """Cutoff passed to repo = today - 7 days at 00:00 Tashkent."""
        frozen_now.return_value = datetime(2026, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)

        mock_user_repo.get_by_manager_id.return_value = [make_user(id=1)]
        mock_course_repo.get_reissuable_by_user_ids.return_value = []

        await add_service.get_reissuable_girls(manager_id=1)

        expected_cutoff = datetime.combine(
            date(2026, 6, 15) - timedelta(days=7),
            dt_time.min,
            tzinfo=TASHKENT_TZ,
        )
        call_kwargs = mock_course_repo.get_reissuable_by_user_ids.call_args
        assert call_kwargs[1]["cutoff"] == expected_cutoff


# =============================================================================
# REISSUE LINK
# =============================================================================


class TestReissueLink:
    async def test_generates_code_and_calls_reissue(
        self,
        add_service: AddService,
        mock_course_repo: AsyncMock,
        fixed_code,
    ):
        expected_course = make_course(id=5, invite_code="FIXEDCODE123")
        mock_course_repo.reissue.return_value = expected_course

        result = await add_service.reissue_link(course_id=5)

        assert result is expected_course
        mock_course_repo.reissue.assert_called_once_with(5, "FIXEDCODE123")