"""Scenario: Girl sends last video → course completed → topic closed.

Tests business rules in one end-to-end flow:
1. Girl sends on-time video on day 20/21 → approved, normal flow
2. Girl sends on-time video on day 21/21 (last day) → approved + COMPLETED
3. Girl receives congratulation message
4. Topic: video + completion text + icon ✅ + CLOSED

Key condition: `next_day >= course.total_days` triggers completion.
After completion no further actions are possible.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from supabase import AsyncClient

from handlers.video.receive import TOPIC_ICON_COMPLETED
from models.video_result import VideoResult
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from services.gemini_service import GeminiService
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

# Base date: course started 20 days ago, current_day=19
BASE_DATE = datetime(2025, 2, 1, tzinfo=TASHKENT_TZ).date()
START_DATE = BASE_DATE - timedelta(days=20)

# Day 20 video — penultimate day
VIDEO_TIME_DAY20 = datetime(2025, 2, 1, 10, 3, tzinfo=TASHKENT_TZ)

# Day 21 video — last day (completion)
VIDEO_TIME_DAY21 = datetime(2025, 2, 2, 10, 5, tzinfo=TASHKENT_TZ)


class TestCompletionScenario:
    """Girl sends last video → course completed → topic closed."""

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
        """Create test data: active course at day 19 (2 days before completion)."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Daria",
            telegram_id=GIRL_TG_ID,
            topic_id=TOPIC_ID,
        )
        course = await create_test_course(
            supabase, user_id=user.id,
            status="active",
            intake_time=INTAKE_TIME.isoformat(),
            start_date=str(START_DATE),
            current_day=19,
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
                    name="Ivanova Daria",
                )
            )

            # ══════════════════════════════════════════════════════════
            # STEP 1: Girl sends on-time video (day 19→20, penultimate)
            # ══════════════════════════════════════════════════════════
            with freeze_time(VIDEO_TIME_DAY20):
                await girl.send_video_note("video_day20")

            # -- DB: day advanced to 20, still active --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 20, f"Expected day 20, got {c.current_day}"
            assert c.status.value == "active", \
                "Course should still be active (not last day yet)"
            assert c.late_count == 0

            # -- DB: intake_log for day 20 --
            log20 = await intake_log_repo.get_by_course_and_day(course.id, 20)
            assert log20 is not None, "IntakeLog for day 20 not found"
            assert log20.video_file_id == "video_day20"
            assert log20.status == "taken"
            assert log20.delay_minutes is not None
            assert log20.delay_minutes <= 30, \
                f"Day 20 should not be late, got {log20.delay_minutes}min"

            # -- Girl: normal approved text (NOT completion) --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.approved(20, TOTAL_DAYS)

            # -- Topic: video_note + approved text --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 2, \
                f"Expected 2 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[0].video_note is not None, \
                "Video note should be sent to topic"
            assert topic_msgs[1].text == VideoTemplates.topic_approved(20, TOTAL_DAYS)

            # -- Topic: NOT closed (regular video doesn't change icon) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert not topic.is_closed, "Topic should NOT be closed yet"

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 2: Girl sends on-time video (day 20→21, LAST DAY)
            # ══════════════════════════════════════════════════════════
            with freeze_time(VIDEO_TIME_DAY21):
                await girl.send_video_note("video_day21_final")

            # -- DB: course COMPLETED --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 21, f"Expected day 21, got {c.current_day}"
            assert c.status.value == "completed", \
                f"Expected completed, got {c.status.value}"
            assert c.late_count == 0
            assert c.appeal_count == 0

            # -- DB: intake_log for day 21 (last day) --
            log21 = await intake_log_repo.get_by_course_and_day(course.id, 21)
            assert log21 is not None, "IntakeLog for day 21 not found"
            assert log21.video_file_id == "video_day21_final"
            assert log21.status == "taken"
            assert log21.delay_minutes is not None
            assert log21.delay_minutes <= 30

            # -- Girl: congratulation message (🎉) --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.private_completed(TOTAL_DAYS)
            assert "Поздравляю" in girl_msg.text
            assert str(TOTAL_DAYS) in girl_msg.text

            # -- Topic: video_note + completion text --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            # 2 from day 20 + 2 from day 21 = 4
            assert len(topic_msgs) == 4, \
                f"Expected 4 topic msgs, got {len(topic_msgs)}"

            # Day 21 video in topic
            assert topic_msgs[2].video_note is not None, \
                "Completion video note should be sent to topic"

            # Completion text
            assert topic_msgs[3].text == VideoTemplates.topic_completed(
                21, TOTAL_DAYS,
            )
            assert "завершена" in topic_msgs[3].text.lower()

            # -- Topic icon → ✅ --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_COMPLETED), \
                "Topic icon should be ✅ after completion"

            # -- Topic CLOSED --
            assert topic.is_closed, \
                "Topic should be closed after course completion"