"""Scenario: Late strikes accumulate without removal in handlers.

Tests business rules in one end-to-end flow:
1. On-time video → approved, day incremented, topic gets video + status
2. Late video (>30min) → approved with late warning, strike 1 recorded
3. Late video → strike 2
4. Late video → strike 3 → course stays ACTIVE (removal handled by workers)
5. late_dates contain exact timestamps at each step
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from supabase import AsyncClient

from models.video_result import VideoResult
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from services.gemini_service import GeminiService
from services.video_service import BASE_MAX_STRIKES
from templates import VideoTemplates
from tests.conftest import create_test_course, create_test_manager, create_test_user
from tests.mock_server import MockTelegramBot
from tests.mock_server.chat_state import ForumTopic
from tests.scenarios.conftest import (
    KOK_GROUP_ID,
    create_scenario_dispatcher,
)
from utils.time import TASHKENT_TZ

# ── Constants ─────────────────────────────────────────────────────────────

GIRL_TG_ID = 555555
MANAGER_TG_ID = 999999
TOPIC_ID = 42
INTAKE_TIME = time(10, 0)  # 10:00 Tashkent
TOTAL_DAYS = 21

# Base date for the scenario
BASE_DATE = datetime(2025, 1, 15, tzinfo=TASHKENT_TZ).date()


def _on_time(day_offset: int) -> datetime:
    """10:05 Tashkent on BASE_DATE + day_offset (5 min delay — not late)."""
    d = BASE_DATE + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, 10, 5, tzinfo=TASHKENT_TZ)


def _late(day_offset: int) -> datetime:
    """10:45 Tashkent on BASE_DATE + day_offset (45 min delay — late!)."""
    d = BASE_DATE + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, 10, 45, tzinfo=TASHKENT_TZ)


class TestStrikeAccumulationScenario:
    """Full end-to-end: 3 late strikes recorded, course stays active."""

    @pytest.fixture
    def gemini_mock(self) -> GeminiService:
        """GeminiService that always approves videos."""
        mock = AsyncMock(spec=GeminiService)
        mock.process_video.return_value = VideoResult(
            approved=True, confidence=0.95, reason="OK",
        )
        return mock

    @pytest.fixture
    async def setup_data(self, supabase: AsyncClient):
        """Create test data: manager, user, active course."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Marina",
            telegram_id=GIRL_TG_ID,
            topic_id=TOPIC_ID,
        )
        course = await create_test_course(
            supabase, user_id=user.id,
            status="active",
            intake_time=INTAKE_TIME.isoformat(),
            start_date=str(BASE_DATE - timedelta(days=3)),
            current_day=2,  # Already did days 1-2
            total_days=TOTAL_DAYS,
            late_count=0,
            appeal_count=0,
        )
        return manager, user, course

    async def test_full_scenario(
        self,
        supabase: AsyncClient,
        gemini_mock: GeminiService,
        setup_data,
    ) -> None:
        manager, user, course = setup_data
        course_repo = CourseRepository(supabase)
        intake_log_repo = IntakeLogRepository(supabase)

        dp = await create_scenario_dispatcher(supabase, gemini_mock)

        async with MockTelegramBot(
            dp, user_id=GIRL_TG_ID,
            chat_id=GIRL_TG_ID,
            chat_type="private",
        ) as girl:
            # Pre-create forum topic so icon changes are tracked
            girl.chat_state._forum_topics.setdefault(KOK_GROUP_ID, {})[TOPIC_ID] = (
                ForumTopic(
                    message_thread_id=TOPIC_ID,
                    chat_id=KOK_GROUP_ID,
                    name="Ivanova Marina",
                )
            )

            # ══════════════════════════════════════════════════════════
            # STEP 1: Day 3 — on-time intake (delay=5min, not late)
            # ══════════════════════════════════════════════════════════
            with freeze_time(_on_time(0)):
                await girl.send_video_note("video_day3")

            # -- DB: course --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 3, f"Expected day 3, got {c.current_day}"
            assert c.status.value == "active"
            assert c.late_count == 0

            # -- DB: intake_log --
            log3 = await intake_log_repo.get_by_course_and_day(course.id, 3)
            assert log3 is not None, "IntakeLog for day 3 not found"
            assert log3.video_file_id == "video_day3"
            assert log3.status == "taken"
            assert log3.delay_minutes is not None
            assert log3.delay_minutes <= 30, f"Day 3 should not be late, got {log3.delay_minutes}min"

            # -- Girl: exact approved text --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.approved(3, TOTAL_DAYS)

            # -- Topic: video_note + approved status text --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 2, f"Expected 2 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[0].video_note is not None, "First topic msg should be video_note"
            assert topic_msgs[1].text == VideoTemplates.topic_approved(3, TOTAL_DAYS)

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 2: Day 4 — late intake (delay=45min) → strike 1
            # ══════════════════════════════════════════════════════════
            with freeze_time(_late(1)):
                await girl.send_video_note("video_day4")

            # -- DB: course --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 4
            assert c.status.value == "active"
            assert c.late_count == 1
            assert len(c.late_dates) == 1

            # -- DB: intake_log --
            log4 = await intake_log_repo.get_by_course_and_day(course.id, 4)
            assert log4 is not None, "IntakeLog for day 4 not found"
            assert log4.video_file_id == "video_day4"
            assert log4.status == "taken"
            assert log4.delay_minutes is not None
            assert log4.delay_minutes > 30, f"Day 4 should be late, got {log4.delay_minutes}min"

            # -- Girl: exact approved_late text --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            max_strikes = BASE_MAX_STRIKES + c.appeal_count  # 3 + 0 = 3
            assert girl_msg.text == VideoTemplates.approved_late(4, TOTAL_DAYS, 1, max_strikes)

            # -- Topic: video + approved + late_warning (3 new msgs, 5 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 5, f"Expected 5 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[2].video_note is not None, "3rd topic msg should be video_note"
            assert topic_msgs[3].text == VideoTemplates.topic_approved(4, TOTAL_DAYS)
            assert topic_msgs[4].text == VideoTemplates.topic_late_warning(1, max_strikes)

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 3: Day 5 — late intake → strike 2
            # ══════════════════════════════════════════════════════════
            with freeze_time(_late(2)):
                await girl.send_video_note("video_day5")

            # -- DB: course --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 5
            assert c.status.value == "active"
            assert c.late_count == 2
            assert len(c.late_dates) == 2

            # -- DB: intake_log --
            log5 = await intake_log_repo.get_by_course_and_day(course.id, 5)
            assert log5 is not None, "IntakeLog for day 5 not found"
            assert log5.video_file_id == "video_day5"
            assert log5.status == "taken"
            assert log5.delay_minutes is not None
            assert log5.delay_minutes > 30

            # -- Girl: exact approved_late text --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.approved_late(5, TOTAL_DAYS, 2, max_strikes)

            # -- Topic: video + approved + late_warning (3 new, 8 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 8, f"Expected 8 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[5].video_note is not None
            assert topic_msgs[6].text == VideoTemplates.topic_approved(5, TOTAL_DAYS)
            assert topic_msgs[7].text == VideoTemplates.topic_late_warning(2, max_strikes)

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 4: Day 6 — late intake → strike 3 → stays ACTIVE
            # Removal is handled by workers, not handlers
            # ══════════════════════════════════════════════════════════
            with freeze_time(_late(3)):
                await girl.send_video_note("video_day6")

            # -- DB: course stays ACTIVE (no removal in handler) --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "active", f"Expected active, got {c.status.value}"
            assert c.current_day == 6, f"Expected day 6, got {c.current_day}"
            assert c.late_count == 3
            assert len(c.late_dates) == 3

            # -- DB: late_dates contain exact timestamps --
            dates_str = VideoTemplates.format_late_dates(c.late_dates)
            assert "16.01 10:45" in dates_str, "Late date 1 missing"
            assert "17.01 10:45" in dates_str, "Late date 2 missing"
            assert "18.01 10:45" in dates_str, "Late date 3 missing"

            # -- DB: intake_log --
            log6 = await intake_log_repo.get_by_course_and_day(course.id, 6)
            assert log6 is not None, "IntakeLog for day 6 not found"
            assert log6.video_file_id == "video_day6"
            assert log6.status == "taken"
            assert log6.delay_minutes > 30

            # -- Girl: late warning (NOT removal) --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.approved_late(6, TOTAL_DAYS, 3, max_strikes)
            assert not girl_msg.has_inline_keyboard(), \
                "No appeal button — handler doesn't remove"

            # -- Topic: video + approved + late_warning (3 new, 11 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 11, f"Expected 11 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[8].video_note is not None
            assert topic_msgs[9].text == VideoTemplates.topic_approved(6, TOTAL_DAYS)
            assert topic_msgs[10].text == VideoTemplates.topic_late_warning(3, max_strikes)
