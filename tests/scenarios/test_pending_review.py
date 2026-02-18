"""Scenario: Gemini rejects video → pending_review → manager confirms → day counted.

Tests business rules in one end-to-end flow:
1. Girl sends on-time video → Gemini not confident → pending_review
2. Girl sees "sent to manager for review" message
3. Topic: video + pending_review text with review buttons
4. Manager DM notification + general topic notification
5. Manager clicks "✅ Принять" → day counted
6. Topic message edited → confirmed text
7. Girl's private message edited → confirmed text

Key: tests the human-in-the-loop path when AI isn't confident,
including manager DM and general topic notifications.
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
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.gemini_service import GeminiService
from templates import VideoTemplates
from tests.conftest import create_test_course, create_test_manager, create_test_user
from tests.mock_server import MockTelegramBot
from tests.mock_server.chat_state import ForumTopic
from tests.mock_server.updates import UpdateBuilder
from tests.scenarios.conftest import (
    KOK_GROUP_ID,
    KOK_GENERAL_TOPIC_ID,
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

# Girl sends video on time
VIDEO_TIME = datetime(2025, 1, 20, 10, 3, tzinfo=TASHKENT_TZ)


class TestPendingReviewScenario:
    """Gemini rejects → pending_review → manager confirms → day counted."""

    @pytest.fixture
    def gemini_mock(self) -> GeminiService:
        """GeminiService that REJECTS the video (low confidence)."""
        mock = AsyncMock(spec=GeminiService)
        mock.process_video.return_value = VideoResult(
            approved=False, confidence=0.3, reason="Не видно таблетку",
        )
        return mock

    @pytest.fixture
    async def setup_data(self, supabase: AsyncClient):
        """Create test data: active course at day 5."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Fedorova Alina",
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
                    name="Fedorova Alina",
                )
            )

            # Manager UpdateBuilder for group chat actions
            mgr_builder = UpdateBuilder(
                user_id=MANAGER_TG_ID,
                chat_id=KOK_GROUP_ID,
                chat_type="supergroup",
                message_thread_id=TOPIC_ID,
            )

            # ══════════════════════════════════════════════════════════
            # STEP 1: Girl sends video → Gemini rejects → pending_review
            # ══════════════════════════════════════════════════════════
            with freeze_time(VIDEO_TIME):
                await girl.send_video_note("video_day6_review")

            # -- DB: course day NOT advanced yet (pending_review) --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 5, \
                "current_day should NOT advance for pending_review"
            assert c.status.value == "active"

            # -- DB: intake_log created with pending_review --
            log6 = await intake_log_repo.get_by_course_and_day(course.id, 6)
            assert log6 is not None, "IntakeLog for day 6 not found"
            assert log6.status == "pending_review"
            assert log6.video_file_id == "video_day6_review"
            assert log6.private_message_id is not None, \
                "private_message_id should be saved for later editing"
            log_id = log6.id
            private_msg_id = log6.private_message_id

            # -- Girl: pending_review message --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.pending_review()

            # -- Topic: video + pending_review text with review buttons --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 2, \
                f"Expected 2 topic msgs (video + review), got {len(topic_msgs)}"

            # Video in topic
            assert topic_msgs[0].video_note is not None, \
                "Video note should be sent to topic"

            # Review message with buttons
            review_msg = topic_msgs[1]
            assert review_msg.text == VideoTemplates.topic_pending_review(
                6, TOTAL_DAYS, "Не видно таблетку",
            )
            assert review_msg.has_inline_keyboard()
            confirm_cb = review_msg.get_button_callback_data("✅ Принять")
            reshoot_cb = review_msg.get_button_callback_data("🔄 Переснять")
            reject_cb = review_msg.get_button_callback_data("❌ Отклонить")
            assert confirm_cb is not None, "Confirm button not found"
            assert reshoot_cb is not None, "Reshoot button not found"
            assert reject_cb is not None, "Reject button not found"
            review_msg_id = review_msg.message_id

            # -- Manager DM notification --
            mgr_dms = girl.chat_state.get_bot_messages(MANAGER_TG_ID)
            assert len(mgr_dms) >= 1, "Manager should receive DM notification"
            mgr_dm = mgr_dms[-1]
            assert "Проверь видео" in mgr_dm.text
            assert "Fedorova Alina" in mgr_dm.text

            # -- General topic notification --
            general_msgs = girl.get_thread_messages(
                KOK_GROUP_ID, KOK_GENERAL_TOPIC_ID,
            )
            assert len(general_msgs) >= 1, \
                "General topic should receive review notification"
            general_msg = general_msgs[-1]
            assert "Test Manager" in general_msg.text
            assert "Fedorova Alina" in general_msg.text
            assert "проверь видео" in general_msg.text

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 2: Manager clicks "✅ Принять" → day counted
            # ══════════════════════════════════════════════════════════
            confirm_update = mgr_builder.make_callback_update(
                callback_data=confirm_cb,
                message_id=review_msg_id,
            )
            await dp.feed_update(girl.bot, confirm_update)

            # -- DB: course day advanced --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 6, f"Expected day 6, got {c.current_day}"
            assert c.status.value == "active"
            assert c.late_count == 0, "On-time video should not add strikes"

            # -- DB: intake_log status → taken --
            log6 = await intake_log_repo.get_by_id(log_id)
            assert log6.status == "taken"

            # -- Topic: review message EDITED to confirmed text --
            edited_review = girl.chat_state.get_message(
                KOK_GROUP_ID, review_msg_id,
            )
            assert edited_review is not None
            assert edited_review.text == VideoTemplates.topic_confirmed(
                6, TOTAL_DAYS,
            )

            # -- Girl: private message EDITED to confirmed text --
            edited_private = girl.chat_state.get_message(
                GIRL_TG_ID, private_msg_id,
            )
            assert edited_private is not None
            assert edited_private.text == VideoTemplates.private_confirmed(
                6, TOTAL_DAYS,
            )
