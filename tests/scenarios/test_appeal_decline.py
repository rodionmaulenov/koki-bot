"""Scenario: 2h no-video removal → appeal → DECLINED → program ended.

Tests business rules in one end-to-end flow:
1. Girl misses intake window → removal_2h worker refuses course
2. Worker sends removal message with appeal button to girl
3. Worker sends removal text to topic + icon ❗️ + closes topic
4. Girl clicks appeal → status=appeal, button removed
5. Appeal FSM: video → text → submitted
6. Topic reopened, icon → ❓, review buttons in topic
7. Manager DECLINES → refused, appeal_count=1, topic icon → ❗️, topic CLOSED
8. Girl receives decline message with manager name
9. Program is permanently ended — no more actions possible

Key difference from removal_appeal: manager DECLINES (not accepts),
course stays refused, topic re-closed with ❗️ icon.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time
from redis.asyncio import Redis
from supabase import AsyncClient

from config import Settings
from handlers.appeal import TOPIC_ICON_APPEAL, TOPIC_ICON_REFUSED
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.gemini_service import GeminiService
from templates import AppealTemplates, WorkerTemplates
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

# Topic icon for refused (from worker module — same as appeal handler)
WORKER_TOPIC_ICON_REFUSED = removal_2h.TOPIC_ICON_REFUSED


class TestAppealDeclineScenario:
    """2h removal → appeal → declined → program permanently ended."""

    @pytest.fixture
    def mock_redis(self) -> Redis:
        """Mock Redis for worker dedup (was_sent=False, mark_sent=OK)."""
        redis = AsyncMock(spec=Redis)
        redis.exists = AsyncMock(return_value=0)  # was_sent → False
        redis.setex = AsyncMock(return_value=True)  # mark_sent → OK
        return redis

    @pytest.fixture
    async def setup_data(self, supabase: AsyncClient):
        """Create test data: manager, user, active course (day 5)."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Sidorova Maria",
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
        mock_redis: Redis,
        setup_data,
    ) -> None:
        manager, user, course = setup_data
        course_repo = CourseRepository(supabase)
        intake_log_repo = IntakeLogRepository(supabase)
        user_repo = UserRepository(supabase)
        manager_repo = ManagerRepository(supabase)

        # GeminiService not needed (no video processing in this scenario)
        gemini_mock = AsyncMock(spec=GeminiService)
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
                    name="Sidorova Maria",
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
            assert c.current_day == 5, "Worker should NOT change current_day"
            assert c.late_count == 0, "Worker should NOT touch late_count"
            assert c.appeal_count == 0, "No appeals yet"

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
            assert topic.icon_custom_emoji_id == str(WORKER_TOPIC_ICON_REFUSED)
            assert topic.is_closed, "Topic should be closed after 2h removal"

            # -- General topic: worker removal notification --
            general_msgs = girl.get_thread_messages(
                KOK_GROUP_ID, KOK_GENERAL_TOPIC_ID,
            )
            assert len(general_msgs) >= 1, \
                "General topic should receive worker removal notification"
            assert "Sidorova Maria" in general_msgs[-1].text
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
            assert c.appeal_count == 0, "appeal_count not incremented until review"

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
            await girl.send_video_note("appeal_video_decline_test")

            # Girl sees ask_text prompt
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == AppealTemplates.ask_text()

            appeal_text = "Я пила таблетку но забыла отправить видео"
            await girl.send_message(appeal_text)

            # -- DB: appeal data saved --
            c = await course_repo.get_by_id(course.id)
            assert c.appeal_video == "appeal_video_decline_test"
            assert c.appeal_text == appeal_text

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
                appeal_text,
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
            assert "Sidorova Maria" in mgr_dms[-1].text

            # -- General topic: appeal notification --
            general_msgs = girl.get_thread_messages(
                KOK_GROUP_ID, KOK_GENERAL_TOPIC_ID,
            )
            # 1 from worker removal + 1 from appeal = at least 2
            assert len(general_msgs) >= 2, \
                "General topic should receive appeal notification"
            assert "Sidorova Maria" in general_msgs[-1].text
            assert "Test Manager" in general_msgs[-1].text

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 4: Manager DECLINES appeal
            # ══════════════════════════════════════════════════════════
            decline_update = mgr_builder.make_callback_update(
                callback_data=decline_cb,
                message_id=appeal_review_msg_id,
            )
            await dp.feed_update(girl.bot, decline_update)

            # -- DB: course refused permanently --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused", \
                f"Expected refused after decline, got {c.status.value}"
            assert c.appeal_count == 1, "appeal_count should be incremented"
            assert c.late_count == 0, "late_count should stay 0"
            assert c.current_day == 5, "current_day unchanged"

            # -- Topic: appeal message EDITED to declined text --
            edited_review = girl.chat_state.get_message(
                KOK_GROUP_ID, appeal_review_msg_id,
            )
            assert edited_review is not None
            assert edited_review.text == AppealTemplates.topic_appeal_declined(
                1, AppealTemplates.MAX_APPEALS,
            )
            # Note: mock server doesn't clear reply_markup when aiogram omits field
            # (reply_markup=None → field not sent). Text check is sufficient.

            # -- Topic icon → ❗️ (refused) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED), \
                "Topic icon should be ❗️ after decline"

            # -- Topic CLOSED after decline --
            assert topic.is_closed, \
                "Topic should be closed after appeal declined"

            # -- Girl: appeal_declined message with manager name --
            girl_msgs = girl.get_bot_messages()
            declined_msgs = [
                m for m in girl_msgs
                if m.text and m.text == AppealTemplates.appeal_declined("Test Manager")
            ]
            assert len(declined_msgs) >= 1, \
                "Girl should receive appeal_declined message"

            # Verify exact decline text includes manager name
            assert "Test Manager" in declined_msgs[0].text
            assert "отклонил" in declined_msgs[0].text

            # ══════════════════════════════════════════════════════════
            # STEP 5: Verify finality — no more actions possible
            # ══════════════════════════════════════════════════════════

            # -- DB: course is refused, appeal_count=1 < MAX_APPEALS=2 --
            # Technically girl has 1 more appeal, but there's no button
            # to trigger it (worker only sends appeal button once).
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused"
            assert c.appeal_count == 1
            remaining_appeals = AppealTemplates.MAX_APPEALS - c.appeal_count
            assert remaining_appeals == 1, \
                "Girl technically has 1 appeal left but no UI to trigger it"

            # -- No appeal button anywhere --
            # Original removal message: button was removed in step 2
            updated_removal = girl.get_message(removal_msg_id)
            assert not updated_removal.has_inline_keyboard(), \
                "Original removal message should have no buttons"

            # -- Topic is closed and icon is ❗️ --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.is_closed, "Topic should remain closed"
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED)

            # -- Topic message count: 3 total (1 worker + 2 appeal) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 3, \
                f"No new topic messages after decline, expected 3, got {len(topic_msgs)}"