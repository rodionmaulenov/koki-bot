"""Scenario: Gemini rejects → pending_review → manager REJECTS → course refused.

Tests business rules in one end-to-end flow:
1. Girl sends video → Gemini rejects (low confidence) → pending_review
2. Manager clicks "Отклонить" → course refused, topic icon ❗️
3. Girl's private message edited to rejected text, NO appeal button
   (removal_reason="manager_reject" — appeal not allowed)

Key difference from test_pending_review: manager clicks REJECT (not confirm).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from supabase import AsyncClient

from handlers.video.review import TOPIC_ICON_REFUSED
from models.video_result import VideoResult
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from services.gemini_service import GeminiService
from templates import VideoTemplates
from tests.conftest import create_test_course, create_test_manager, create_test_user
from tests.mock_server import MockTelegramBot
from tests.mock_server.chat_state import ForumTopic
from tests.mock_server.updates import UpdateBuilder
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

# Girl sends video on time (within window)
VIDEO_TIME = datetime(2025, 1, 20, 10, 5, tzinfo=TASHKENT_TZ)


class TestVideoRejectedScenario:
    """Gemini rejects → manager rejects → appeal → accepted."""

    @pytest.fixture
    def gemini_mock(self) -> GeminiService:
        """GeminiService that rejects video (low confidence)."""
        mock = AsyncMock(spec=GeminiService)
        mock.process_video.return_value = VideoResult(
            approved=False, confidence=0.3, reason="Cannot see pill",
        )
        return mock

    @pytest.fixture
    async def setup_data(self, supabase: AsyncClient):
        """Create test data: manager, user, active course (day 5)."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Kuznetsova Anna",
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
                    name="Kuznetsova Anna",
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
                await girl.send_video_note("video_day6_rejected")

            # -- DB: intake_log created with pending_review --
            log = await intake_log_repo.get_by_course_and_day(course.id, 6)
            assert log is not None, "IntakeLog for day 6 not found"
            assert log.status == "pending_review"
            assert log.video_file_id == "video_day6_rejected"
            assert log.private_message_id is not None
            private_msg_id = log.private_message_id

            # -- DB: course day NOT advanced (pending) --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 5, "Day should NOT advance for pending_review"
            assert c.status.value == "active"

            # -- Girl: sees pending_review message --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.pending_review()

            # -- Topic: video + pending text with review buttons --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 2, f"Expected 2 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[0].video_note is not None
            review_msg = topic_msgs[1]
            assert review_msg.has_inline_keyboard()
            reject_cb = review_msg.get_button_callback_data("Отклонить")
            assert reject_cb is not None, "Reject button not found"
            review_msg_id = review_msg.message_id

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 2: Manager REJECTS video
            # ══════════════════════════════════════════════════════════
            reject_update = mgr_builder.make_callback_update(
                callback_data=reject_cb,
                message_id=review_msg_id,
            )
            await dp.feed_update(girl.bot, reject_update)

            # -- DB: course REFUSED --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused", \
                f"Expected refused after reject, got {c.status.value}"
            assert c.current_day == 5, "Day should stay at 5"
            assert c.appeal_count == 0, "No appeals yet"

            # -- DB: intake_log status = rejected --
            log = await intake_log_repo.get_by_id(log.id)
            assert log.status == "rejected"

            # -- Topic: review message EDITED to rejected text --
            edited_review = girl.chat_state.get_message(
                KOK_GROUP_ID, review_msg_id,
            )
            assert edited_review is not None
            assert edited_review.text == VideoTemplates.topic_rejected()

            # -- Topic icon → ❗️ --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED)

            # -- Girl: private message EDITED to rejected, NO appeal button --
            # removal_reason="manager_reject" → appeal not allowed
            edited_private = girl.get_message(private_msg_id)
            assert edited_private is not None
            assert edited_private.text == VideoTemplates.private_rejected("Test Manager")
            assert not edited_private.has_inline_keyboard(), \
                "Should NOT have appeal button (manager_reject → no appeal)"

            # -- DB: course stays refused, no appeal --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused"
            assert c.appeal_count == 0