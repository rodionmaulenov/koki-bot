"""Scenario: Edge cases — late video on the last day.

Two sub-tests:
1. Last day + 1st late strike → COMPLETION wins (late_count < max_strikes)
2. Last day + 3rd late strike → REMOVAL wins (late_count >= max_strikes)

Key insight: `is_removal` is checked BEFORE `is_completed`.
is_completed = approved AND NOT is_removal AND next_day >= total_days
So if is_removal=True, completion is impossible — even on the last day.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from supabase import AsyncClient

from handlers.video.receive import TOPIC_ICON_COMPLETED, TOPIC_ICON_REFUSED
from models.video_result import VideoResult
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
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

BASE_DATE = datetime(2025, 2, 10, tzinfo=TASHKENT_TZ).date()

# Girl sends video 35 minutes late on the last day
LATE_VIDEO_TIME = datetime(2025, 2, 10, 10, 35, tzinfo=TASHKENT_TZ)


def _gemini_approves() -> GeminiService:
    mock = AsyncMock(spec=GeminiService)
    mock.process_video.return_value = VideoResult(
        approved=True, confidence=0.95, reason="OK",
    )
    return mock


class TestLateLastDayCompletion:
    """Last day + 1st late strike → COMPLETION wins."""

    @pytest.fixture
    async def setup_data(self, supabase: AsyncClient):
        """Course at day 20/21, no prior strikes."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Volkova Olga",
            telegram_id=GIRL_TG_ID,
            topic_id=TOPIC_ID,
        )
        course = await create_test_course(
            supabase, user_id=user.id,
            status="active",
            intake_time=INTAKE_TIME.isoformat(),
            start_date=str(BASE_DATE - timedelta(days=21)),
            current_day=20,
            total_days=TOTAL_DAYS,
            late_count=0,
            appeal_count=0,
        )
        return manager, user, course

    async def test_late_last_day_completes(
        self,
        supabase: AsyncClient,
        setup_data,
    ) -> None:
        """Late on last day with strikes < max → course COMPLETES."""
        manager, user, course = setup_data
        course_repo = CourseRepository(supabase)
        intake_log_repo = IntakeLogRepository(supabase)

        gemini_mock = _gemini_approves()
        dp = await create_scenario_dispatcher(supabase, gemini_mock)

        async with MockTelegramBot(
            dp, user_id=GIRL_TG_ID,
            chat_id=GIRL_TG_ID,
            chat_type="private",
        ) as girl:
            girl.chat_state._forum_topics.setdefault(KOK_GROUP_ID, {})[TOPIC_ID] = (
                ForumTopic(
                    message_thread_id=TOPIC_ID,
                    chat_id=KOK_GROUP_ID,
                    name="Volkova Olga",
                )
            )

            with freeze_time(LATE_VIDEO_TIME):
                await girl.send_video_note("video_day21_late")

            # -- DB: COMPLETED (not removed) --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "completed", \
                f"Expected completed, got {c.status.value}"
            assert c.current_day == 21
            assert c.late_count == 1, "Late should be recorded even on completion"

            # -- DB: intake_log --
            log21 = await intake_log_repo.get_by_course_and_day(course.id, 21)
            assert log21 is not None
            assert log21.status == "taken"
            assert log21.delay_minutes >= 30

            # -- Girl: congratulation (completion, not late warning) --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg.text == VideoTemplates.private_completed(TOTAL_DAYS)

            # -- Topic: video + completion text + icon ✅ + CLOSED --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 2  # video + completion text
            assert topic_msgs[1].text == VideoTemplates.topic_completed(
                21, TOTAL_DAYS,
            )

            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_COMPLETED)
            assert topic.is_closed


class TestLateLastDayRemoval:
    """Last day + 3rd late strike → REMOVAL wins over completion."""

    @pytest.fixture
    async def setup_data(self, supabase: AsyncClient):
        """Course at day 20/21, already has 2 strikes (max_strikes=3)."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Sokolova Anya",
            telegram_id=GIRL_TG_ID,
            topic_id=TOPIC_ID,
        )
        course = await create_test_course(
            supabase, user_id=user.id,
            status="active",
            intake_time=INTAKE_TIME.isoformat(),
            start_date=str(BASE_DATE - timedelta(days=21)),
            current_day=20,
            total_days=TOTAL_DAYS,
            late_count=2,
            appeal_count=0,
        )
        return manager, user, course

    async def test_late_last_day_removal_wins(
        self,
        supabase: AsyncClient,
        setup_data,
    ) -> None:
        """Late on last day with strikes >= max → REMOVAL, not completion."""
        manager, user, course = setup_data
        course_repo = CourseRepository(supabase)
        intake_log_repo = IntakeLogRepository(supabase)
        manager_repo = ManagerRepository(supabase)

        gemini_mock = _gemini_approves()
        dp = await create_scenario_dispatcher(supabase, gemini_mock)

        async with MockTelegramBot(
            dp, user_id=GIRL_TG_ID,
            chat_id=GIRL_TG_ID,
            chat_type="private",
        ) as girl:
            girl.chat_state._forum_topics.setdefault(KOK_GROUP_ID, {})[TOPIC_ID] = (
                ForumTopic(
                    message_thread_id=TOPIC_ID,
                    chat_id=KOK_GROUP_ID,
                    name="Sokolova Anya",
                )
            )

            with freeze_time(LATE_VIDEO_TIME):
                await girl.send_video_note("video_day21_late_removal")

            max_strikes = BASE_MAX_STRIKES  # 3

            # -- DB: REFUSED (not completed!) --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused", \
                f"Expected refused (removal wins), got {c.status.value}"
            # undo_day_and_refuse rolls back to pre-record state
            assert c.current_day == 20, \
                "current_day should be rolled back after removal"
            assert c.late_count == 3, \
                f"Expected late_count=3, got {c.late_count}"

            # -- Girl: removal message (NOT completion!) --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            # Verify it's a removal message, not congratulation
            assert "Поздравляю" not in girl_msg.text, \
                "Should NOT show completion message"
            # Should have late dates in the removal text
            assert "Test Manager" in girl_msg.text

            # Verify appeal button present (appeal_count=0 < MAX_APPEALS)
            assert girl_msg.has_inline_keyboard(), \
                "Appeal button should be present"
            appeal_cb = girl_msg.get_button_callback_data("Апелляция")
            assert appeal_cb is not None

            # -- Topic: removal, NOT completion --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            # Video is sent to topic first, then removal info
            assert len(topic_msgs) >= 1
            # Last topic message should NOT be completion
            last_topic = topic_msgs[-1]
            assert "завершена! ✅" not in (last_topic.text or ""), \
                "Topic should NOT show completion message"

            # -- Topic icon → ❗️ (refused, NOT ✅) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED), \
                "Topic icon should be ❗️ (refused), not ✅ (completed)"
