"""Scenario: Girl sends late video (35 min) → approved with warning, no removal.

Tests business rules in one end-to-end flow:
1. Girl sends video 35 minutes late → Gemini approves
2. Day counted, but late_count incremented to 1
3. Girl sees approved_late message with remaining strikes
4. Topic: video + approved text + late warning message
5. late_dates updated with timestamp

Key: tests the late warning path WITHOUT removal (late_count < max_strikes).
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

BASE_DATE = datetime(2025, 1, 20, tzinfo=TASHKENT_TZ).date()

# Girl sends video 35 minutes late (10:00 + 35min = 10:35)
LATE_VIDEO_TIME = datetime(2025, 1, 20, 10, 35, tzinfo=TASHKENT_TZ)


class TestLateWarningScenario:
    """Late video → approved with warning, no removal."""

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
        """Create test data: active course at day 5, no prior strikes."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Morozova Katya",
            telegram_id=GIRL_TG_ID,
            topic_id=TOPIC_ID,
        )
        course = await create_test_course(
            supabase, user_id=user.id,
            status="active",
            intake_time=INTAKE_TIME.isoformat(),
            start_date=str(BASE_DATE - timedelta(days=6)),
            current_day=5,
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
            # Pre-create forum topic
            girl.chat_state._forum_topics.setdefault(KOK_GROUP_ID, {})[TOPIC_ID] = (
                ForumTopic(
                    message_thread_id=TOPIC_ID,
                    chat_id=KOK_GROUP_ID,
                    name="Morozova Katya",
                )
            )

            # ══════════════════════════════════════════════════════════
            # STEP 1: Girl sends video 35 min late → approved with warning
            # ══════════════════════════════════════════════════════════
            with freeze_time(LATE_VIDEO_TIME):
                await girl.send_video_note("video_day6_late")

            max_strikes = BASE_MAX_STRIKES  # 3 (no appeals)

            # -- DB: day advanced (video approved despite late) --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 6, f"Expected day 6, got {c.current_day}"
            assert c.status.value == "active", \
                "Course should still be active (1 strike < max_strikes)"

            # -- DB: late_count incremented --
            assert c.late_count == 1, \
                f"Expected late_count=1, got {c.late_count}"

            # -- DB: late_dates has one entry --
            assert len(c.late_dates) == 1, \
                f"Expected 1 late_date, got {len(c.late_dates)}"

            # -- DB: intake_log --
            log6 = await intake_log_repo.get_by_course_and_day(course.id, 6)
            assert log6 is not None
            assert log6.status == "taken"
            assert log6.video_file_id == "video_day6_late"
            assert log6.delay_minutes is not None
            assert log6.delay_minutes >= 30, \
                f"Expected delay >= 30min, got {log6.delay_minutes}"

            # -- Girl: approved_late message with remaining strikes --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.approved_late(
                6, TOTAL_DAYS, 1, max_strikes,
            )
            # Verify it mentions remaining strikes
            remaining = max_strikes - 1
            assert str(remaining) in girl_msg.text

            # -- Topic: video + approved text + late warning --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            # 1 video + 1 approved text + 1 late warning = 3
            assert len(topic_msgs) == 3, \
                f"Expected 3 topic msgs, got {len(topic_msgs)}"

            # Video in topic
            assert topic_msgs[0].video_note is not None

            # Approved text (normal approved, not late-specific)
            assert topic_msgs[1].text == VideoTemplates.topic_approved(
                6, TOTAL_DAYS,
            )

            # Late warning message (separate from approved)
            assert topic_msgs[2].text == VideoTemplates.topic_late_warning(
                1, max_strikes,
            )
            assert "Опоздание" in topic_msgs[2].text
            assert "1/3" in topic_msgs[2].text