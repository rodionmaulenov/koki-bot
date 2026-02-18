"""Scenario: Gemini rejects → pending_review → manager reshoots → girl resends → approved.

Tests business rules in one end-to-end flow:
1. Girl sends video → Gemini rejects → pending_review
2. Manager clicks "🔄 Переснять" → reshoot status, deadline set
3. Girl's private message edited → reshoot instructions
4. Topic icon → 💡 (reshoot waiting)
5. Girl resends video → Gemini approves → day counted
6. Topic: new video + approved text, icon → 💊

Key: tests the reshoot path — manager requests reshoot,
girl gets a deadline, resends video, AI approves.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from supabase import AsyncClient

from handlers.video.receive import TOPIC_ICON_ACTIVE
from handlers.video.review import TOPIC_ICON_RESHOOT
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

# Girl sends first video on time
VIDEO_TIME = datetime(2025, 1, 20, 10, 3, tzinfo=TASHKENT_TZ)

# Girl resends video after reshoot request (30 min later)
RESHOOT_VIDEO_TIME = datetime(2025, 1, 20, 10, 35, tzinfo=TASHKENT_TZ)


class TestReshootScenario:
    """Gemini rejects → reshoot → girl resends → approved."""

    @pytest.fixture
    def gemini_mock(self) -> GeminiService:
        """GeminiService: first call rejects, second call approves."""
        mock = AsyncMock(spec=GeminiService)
        mock.process_video.side_effect = [
            # First call: rejects
            VideoResult(approved=False, confidence=0.3, reason="Плохое качество"),
            # Second call: approves reshoot video
            VideoResult(approved=True, confidence=0.92, reason="OK"),
        ]
        return mock

    @pytest.fixture
    async def setup_data(self, supabase: AsyncClient):
        """Create test data: active course at day 5."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Kuznetsova Daria",
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
                    name="Kuznetsova Daria",
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
                await girl.send_video_note("video_day6_bad")

            # -- DB: pending_review --
            log6 = await intake_log_repo.get_by_course_and_day(course.id, 6)
            assert log6 is not None
            assert log6.status == "pending_review"
            assert log6.private_message_id is not None
            log_id = log6.id
            private_msg_id = log6.private_message_id

            # -- Girl: pending_review message --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg.text == VideoTemplates.pending_review()

            # -- Topic: video + review buttons --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 2
            review_msg = topic_msgs[1]
            assert review_msg.has_inline_keyboard()
            reshoot_cb = review_msg.get_button_callback_data("🔄 Переснять")
            assert reshoot_cb is not None
            review_msg_id = review_msg.message_id

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 2: Manager clicks "🔄 Переснять"
            # ══════════════════════════════════════════════════════════
            with freeze_time(VIDEO_TIME):
                reshoot_update = mgr_builder.make_callback_update(
                    callback_data=reshoot_cb,
                    message_id=review_msg_id,
                )
                await dp.feed_update(girl.bot, reshoot_update)

            # -- DB: intake_log → reshoot, deadline set --
            log6 = await intake_log_repo.get_by_id(log_id)
            assert log6.status == "reshoot"
            assert log6.reshoot_deadline is not None

            # -- Topic message EDITED → reshoot text --
            edited_review = girl.chat_state.get_message(
                KOK_GROUP_ID, review_msg_id,
            )
            assert edited_review is not None
            assert "переснять" in edited_review.text.lower()
            assert "День 6" in edited_review.text

            # -- Girl: private message EDITED → reshoot instructions --
            edited_private = girl.chat_state.get_message(
                GIRL_TG_ID, private_msg_id,
            )
            assert edited_private is not None
            assert "переснять" in edited_private.text.lower()
            assert "отправь сюда" in edited_private.text.lower()

            # -- Topic icon → 💡 (reshoot waiting) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_RESHOOT), \
                "Topic icon should be 💡 during reshoot"

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 3: Girl resends video → Gemini approves → day counted
            # ══════════════════════════════════════════════════════════
            with freeze_time(RESHOOT_VIDEO_TIME):
                await girl.send_video_note("video_day6_reshoot")

            # -- DB: course day advanced --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 6, f"Expected day 6, got {c.current_day}"
            assert c.status.value == "active"

            # -- DB: intake_log updated (same record, not new) --
            log6 = await intake_log_repo.get_by_id(log_id)
            assert log6.status == "taken", \
                f"Expected taken after reshoot approved, got {log6.status}"
            assert log6.video_file_id == "video_day6_reshoot", \
                "video_file_id should be updated to reshoot video"

            # -- Girl: approved message --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg.text == VideoTemplates.approved(6, TOTAL_DAYS)

            # -- Topic: reshoot video + approved text (4 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            # 2 from step 1 + 2 from step 3 = 4
            assert len(topic_msgs) == 4, \
                f"Expected 4 topic msgs, got {len(topic_msgs)}"

            # Reshoot video in topic
            assert topic_msgs[2].video_note is not None, \
                "Reshoot video note should be sent to topic"

            # Approved text
            assert topic_msgs[3].text == VideoTemplates.topic_approved(
                6, TOTAL_DAYS,
            )

            # -- Topic icon → 💊 (reshoot approved → back to active) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_ACTIVE), \
                "Topic icon should be 💊 after reshoot approved"