"""Scenario: 2h no-video removal → appeal → accepted → girl continues next day.

Tests business rules in one end-to-end flow:
1. Girl misses intake window → removal_2h worker refuses course
2. Worker sends removal message with appeal button to girl
3. Worker sends removal text to topic + icon ❗️ + closes topic
4. Girl clicks appeal → status=appeal, button removed
5. Appeal FSM: video → text → submitted
6. Topic reopened, icon → ❓, review buttons in topic
7. Manager accepts → active, appeal_count=1, topic icon → 💊
8. Next day girl sends on-time video → approved, day incremented

Key difference from strike_appeal: removal via WORKER (not handler),
late_count stays 0, topic is CLOSED after removal then REOPENED for appeal.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time
from redis.asyncio import Redis
from supabase import AsyncClient

from config import Settings
from handlers.appeal.submit import TOPIC_ICON_APPEAL
from handlers.video.receive import TOPIC_ICON_ACTIVE
from models.video_result import VideoResult
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.gemini_service import GeminiService
from services.video_service import BASE_MAX_STRIKES
from templates import AppealTemplates, VideoTemplates, WorkerTemplates
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
from workers.tasks import removal_2h

# ── Constants ─────────────────────────────────────────────────────────────

GIRL_TG_ID = 555555
MANAGER_TG_ID = 999999
TOPIC_ID = 42
INTAKE_TIME = time(10, 0)  # 10:00 Tashkent
TOTAL_DAYS = 21

# Base date for the scenario
BASE_DATE = datetime(2025, 1, 15, tzinfo=TASHKENT_TZ).date()

# Worker runs 2h after intake_time
WORKER_TIME = datetime(2025, 1, 15, 12, 0, tzinfo=TASHKENT_TZ)

# Next day girl sends video on time
NEXT_DAY_VIDEO_TIME = datetime(2025, 1, 16, 10, 5, tzinfo=TASHKENT_TZ)

# Topic icon for refused (from worker module)
TOPIC_ICON_REFUSED = removal_2h.TOPIC_ICON_REFUSED


class TestRemovalAppealScenario:
    """2h removal → appeal → accepted → girl sends video next day."""

    @pytest.fixture
    def gemini_mock(self) -> GeminiService:
        """GeminiService that always approves videos."""
        mock = AsyncMock(spec=GeminiService)
        mock.process_video.return_value = VideoResult(
            approved=True, confidence=0.95, reason="OK",
        )
        return mock

    @pytest.fixture
    def mock_redis(self) -> Redis:
        """Mock Redis for worker dedup (was_sent=False, mark_sent=OK)."""
        redis = AsyncMock(spec=Redis)
        redis.exists = AsyncMock(return_value=0)  # was_sent → False
        redis.setex = AsyncMock(return_value=True)  # mark_sent → OK
        return redis

    @pytest.fixture
    async def setup_data(self, supabase: AsyncClient):
        """Create test data: manager, user, active course (day 2)."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Petrova Elena",
            telegram_id=GIRL_TG_ID,
            topic_id=TOPIC_ID,
        )
        course = await create_test_course(
            supabase, user_id=user.id,
            status="active",
            intake_time=INTAKE_TIME.isoformat(),
            start_date=str(BASE_DATE - timedelta(days=3)),
            current_day=2,
            total_days=TOTAL_DAYS,
            late_count=0,
            appeal_count=0,
        )
        return manager, user, course

    async def test_full_scenario(
        self,
        supabase: AsyncClient,
        gemini_mock: GeminiService,
        mock_redis: Redis,
        setup_data,
    ) -> None:
        manager, user, course = setup_data
        course_repo = CourseRepository(supabase)
        intake_log_repo = IntakeLogRepository(supabase)
        user_repo = UserRepository(supabase)
        manager_repo = ManagerRepository(supabase)

        dp = await create_scenario_dispatcher(supabase, gemini_mock)

        # Worker needs its own settings mock (worker bypasses Dishka)
        worker_settings = MagicMock(spec=Settings)
        worker_settings.kok_group_id = KOK_GROUP_ID
        worker_settings.kok_general_topic_id = KOK_GENERAL_TOPIC_ID

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
                    name="Petrova Elena",
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
            # STEP 1: Worker removes course (12:00 — 2h after intake)
            # ══════════════════════════════════════════════════════════
            with freeze_time(WORKER_TIME):
                await removal_2h.run(
                    bot=girl.bot,
                    redis=mock_redis,
                    settings=worker_settings,
                    course_repository=course_repo,
                    user_repository=user_repo,
                    manager_repository=manager_repo,
                    intake_log_repository=intake_log_repo,
                )

            # -- DB: course refused, late_count unchanged --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused", f"Expected refused, got {c.status.value}"
            assert c.current_day == 2, "Worker should NOT change current_day"
            assert c.late_count == 0, "Worker should NOT touch late_count"

            # -- Girl: removal message + appeal button --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == WorkerTemplates.removal_no_video("Test Manager")
            assert girl_msg.has_inline_keyboard(), "Girl should see appeal button"
            appeal_cb = girl_msg.get_button_callback_data("Апелляция")
            assert appeal_cb is not None, "Appeal button not found"
            removal_msg_id = girl_msg.message_id

            # -- Topic: removal text --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 1, f"Expected 1 topic msg, got {len(topic_msgs)}"
            assert topic_msgs[0].text == WorkerTemplates.topic_removal_no_video()

            # -- Topic: icon → ❗️ + CLOSED --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED)
            assert topic.is_closed, "Topic should be closed after 2h removal"

            # -- General topic: worker removal notification --
            general_msgs = girl.get_thread_messages(
                KOK_GROUP_ID, KOK_GENERAL_TOPIC_ID,
            )
            assert len(general_msgs) >= 1, \
                "General topic should receive worker removal notification"
            assert "Petrova Elena" in general_msgs[-1].text
            assert "снята" in general_msgs[-1].text
            assert "не отправила видео" in general_msgs[-1].text

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 2: Girl starts appeal
            # ══════════════════════════════════════════════════════════
            await girl.click_button(appeal_cb, removal_msg_id)

            # -- DB: status changed --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "appeal"

            # -- Girl: appeal button REMOVED from worker message --
            updated_removal = girl.get_message(removal_msg_id)
            assert updated_removal is not None
            assert not updated_removal.has_inline_keyboard(), \
                "Appeal button should be removed after clicking"

            # -- Girl: sees ask_video prompt --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == AppealTemplates.ask_video()

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 3: Girl sends appeal video + text
            # ══════════════════════════════════════════════════════════
            await girl.send_video_note("appeal_video_2h")

            # Girl sees ask_text prompt
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == AppealTemplates.ask_text()

            await girl.send_message("Забыла отправить, прошу вернуть")

            # -- DB: appeal data saved --
            c = await course_repo.get_by_id(course.id)
            assert c.appeal_video == "appeal_video_2h"
            assert c.appeal_text == "Забыла отправить, прошу вернуть"

            # -- Girl: appeal_submitted confirmation --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == AppealTemplates.appeal_submitted()

            # -- Topic: REOPENED + icon → ❓ --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_APPEAL)
            assert not topic.is_closed, \
                "Topic should be reopened after appeal submitted"

            # -- Topic: appeal video + appeal text with buttons --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            # 1 from worker + 2 from appeal = 3
            assert len(topic_msgs) == 3, f"Expected 3 topic msgs, got {len(topic_msgs)}"

            # Appeal video in topic
            assert topic_msgs[1].video is not None, \
                "Appeal video should be sent to topic"

            # Appeal text with review buttons
            appeal_review_msg = topic_msgs[2]
            assert appeal_review_msg.text == AppealTemplates.topic_appeal_submitted(
                "Забыла отправить, прошу вернуть",
            )
            assert appeal_review_msg.has_inline_keyboard()
            accept_cb = appeal_review_msg.get_button_callback_data("Принять")
            decline_cb = appeal_review_msg.get_button_callback_data("Отклонить")
            assert accept_cb is not None, "Accept button not found"
            assert decline_cb is not None, "Decline button not found"
            appeal_review_msg_id = appeal_review_msg.message_id

            # -- Manager DM: appeal notification --
            mgr_dms = girl.chat_state.get_bot_messages(MANAGER_TG_ID)
            assert len(mgr_dms) >= 1, "Manager should receive appeal DM"
            assert "Petrova Elena" in mgr_dms[-1].text

            # -- General topic: appeal notification --
            general_msgs = girl.get_thread_messages(
                KOK_GROUP_ID, KOK_GENERAL_TOPIC_ID,
            )
            # 1 from worker removal + 1 from appeal = at least 2
            assert len(general_msgs) >= 2, \
                "General topic should receive appeal notification"
            assert "Petrova Elena" in general_msgs[-1].text
            assert "Test Manager" in general_msgs[-1].text

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 4: Manager accepts appeal
            # ══════════════════════════════════════════════════════════
            accept_update = mgr_builder.make_callback_update(
                callback_data=accept_cb,
                message_id=appeal_review_msg_id,
            )
            await dp.feed_update(girl.bot, accept_update)

            # -- DB: course reactivated --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "active", f"Expected active, got {c.status.value}"
            assert c.appeal_count == 1
            assert c.late_count == 0, "late_count should stay 0 (2h removal doesn't add strikes)"
            assert c.current_day == 2, "current_day unchanged (was 2 before removal)"

            # -- Dynamic threshold: max_strikes = 3 + 1 = 4 --
            new_max = BASE_MAX_STRIKES + c.appeal_count
            assert new_max == 4

            # -- Topic: appeal message EDITED to accepted --
            edited_review = girl.chat_state.get_message(
                KOK_GROUP_ID, appeal_review_msg_id,
            )
            assert edited_review is not None
            assert edited_review.text == AppealTemplates.topic_appeal_accepted(
                1, AppealTemplates.MAX_APPEALS,
            )

            # -- Topic icon → 💊 (active again) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_ACTIVE)

            # -- Girl: appeal_accepted message --
            girl_msgs = girl.get_bot_messages()
            accepted_msgs = [
                m for m in girl_msgs
                if m.text and m.text == AppealTemplates.appeal_accepted(1)
            ]
            assert len(accepted_msgs) >= 1, "Girl should receive appeal_accepted message"

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 5: Next day — girl sends on-time video → approved
            # ══════════════════════════════════════════════════════════
            with freeze_time(NEXT_DAY_VIDEO_TIME):
                await girl.send_video_note("video_day3")

            # -- DB: course progressed --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 3, f"Expected day 3, got {c.current_day}"
            assert c.status.value == "active"
            assert c.late_count == 0, "On-time video should not add strikes"

            # -- DB: intake_log --
            log3 = await intake_log_repo.get_by_course_and_day(course.id, 3)
            assert log3 is not None, "IntakeLog for day 3 not found"
            assert log3.video_file_id == "video_day3"
            assert log3.status == "taken"
            assert log3.delay_minutes is not None
            assert log3.delay_minutes <= 30, \
                f"Day 3 should not be late, got {log3.delay_minutes}min"

            # -- Girl: exact approved text --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.approved(3, TOTAL_DAYS)

            # -- Topic: video_note + approved (2 new, 5 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            # 1 worker + 2 appeal + 2 video = 5
            assert len(topic_msgs) == 5, f"Expected 5 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[3].video_note is not None, \
                "Video note should be sent to topic"
            assert topic_msgs[4].text == VideoTemplates.topic_approved(3, TOTAL_DAYS)