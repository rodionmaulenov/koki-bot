"""Scenario: MAX_APPEALS exhausted → third removal has no appeal button.

Tests business rules in one end-to-end flow:
1. Course already has appeal_count=1 (first appeal was used earlier)
2. Worker 2h removal → appeal button IS present (1 < MAX_APPEALS=2)
3. Girl appeals → video → text → submitted → topic reopened
4. Manager accepts → appeal_count=2, girl gets "last chance" warning
5. Girl sends on-time video next day → day advances
6. Worker 2h removal again → NO appeal button (2 >= MAX_APPEALS=2)
7. Program permanently ended — no UI to trigger appeal

Key thing tested: the `appeal_count < MAX_APPEALS` guard in worker
and the "last chance" warning in appeal_accepted(2).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time
from redis.asyncio import Redis
from supabase import AsyncClient

from config import Settings
from handlers.appeal.review import TOPIC_ICON_REFUSED
from handlers.appeal.submit import TOPIC_ICON_APPEAL
from handlers.video.receive import TOPIC_ICON_ACTIVE
from models.video_result import VideoResult
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.gemini_service import GeminiService
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

# Step 1: Worker runs 2h after intake
WORKER_TIME_DAY1 = datetime(2025, 1, 15, 12, 0, tzinfo=TASHKENT_TZ)

# Step 5: Girl sends video next day on time
NEXT_DAY_VIDEO_TIME = datetime(2025, 1, 16, 10, 5, tzinfo=TASHKENT_TZ)

# Step 6: Worker runs again 2 days later (girl didn't send video)
WORKER_TIME_DAY3 = datetime(2025, 1, 17, 12, 0, tzinfo=TASHKENT_TZ)

WORKER_TOPIC_ICON_REFUSED = removal_2h.TOPIC_ICON_REFUSED


class TestMaxAppealsScenario:
    """2 appeals exhausted → third removal has no appeal button."""

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
        """Create test data: course with appeal_count=1 (one appeal already used)."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Kozlova Anna",
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
            appeal_count=1,  # First appeal already used!
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
                    name="Kozlova Anna",
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
            # STEP 1: Worker removes course (appeal_count=1, still eligible)
            # ══════════════════════════════════════════════════════════
            with freeze_time(WORKER_TIME_DAY1):
                await removal_2h.run(
                    bot=girl.bot,
                    redis=mock_redis,
                    settings=worker_settings,
                    course_repository=course_repo,
                    user_repository=user_repo,
                    manager_repository=manager_repo,
                    intake_log_repository=intake_log_repo,
                )

            # -- DB: course refused --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused"
            assert c.appeal_count == 1, "appeal_count unchanged by worker"
            assert c.current_day == 5

            # -- Girl: removal message WITH appeal button --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == WorkerTemplates.removal_no_video("Test Manager")
            assert girl_msg.has_inline_keyboard(), \
                "Appeal button should be present (appeal_count=1 < MAX_APPEALS=2)"
            appeal_cb = girl_msg.get_button_callback_data("Апелляция")
            assert appeal_cb is not None
            removal_msg_id_1 = girl_msg.message_id

            # -- Topic: removal text + icon ❗️ + CLOSED --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 1
            assert topic_msgs[0].text == WorkerTemplates.topic_removal_no_video()

            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.icon_custom_emoji_id == str(WORKER_TOPIC_ICON_REFUSED)
            assert topic.is_closed

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 2: Girl appeals (video + text)
            # ══════════════════════════════════════════════════════════
            await girl.click_button(appeal_cb, removal_msg_id_1)

            # -- DB: status=appeal --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "appeal"

            # -- Girl: button removed, ask_video --
            updated_removal = girl.get_message(removal_msg_id_1)
            assert not updated_removal.has_inline_keyboard()

            girl_msg = girl.get_last_bot_message()
            assert girl_msg.text == AppealTemplates.ask_video()

            girl.clear_requests_only()

            # -- Appeal FSM: video → text --
            await girl.send_video_note("appeal_video_max")

            girl_msg = girl.get_last_bot_message()
            assert girl_msg.text == AppealTemplates.ask_text()

            appeal_text = "Пожалуйста, верните меня в программу"
            await girl.send_message(appeal_text)

            # -- DB: appeal data saved --
            c = await course_repo.get_by_id(course.id)
            assert c.appeal_video == "appeal_video_max"
            assert c.appeal_text == appeal_text

            # -- Girl: appeal_submitted --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg.text == AppealTemplates.appeal_submitted()

            # -- Topic: REOPENED, icon ❓, video + review buttons --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_APPEAL)
            assert not topic.is_closed

            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            # 1 worker + 2 appeal = 3
            assert len(topic_msgs) == 3

            assert topic_msgs[1].video is not None
            appeal_review_msg = topic_msgs[2]
            assert appeal_review_msg.text == AppealTemplates.topic_appeal_submitted(
                appeal_text,
            )
            assert appeal_review_msg.has_inline_keyboard()
            accept_cb = appeal_review_msg.get_button_callback_data("Принять")
            assert accept_cb is not None
            appeal_review_msg_id = appeal_review_msg.message_id

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 3: Manager accepts → appeal_count=2 ("last chance")
            # ══════════════════════════════════════════════════════════
            accept_update = mgr_builder.make_callback_update(
                callback_data=accept_cb,
                message_id=appeal_review_msg_id,
            )
            await dp.feed_update(girl.bot, accept_update)

            # -- DB: active, appeal_count=2 --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "active"
            assert c.appeal_count == 2, \
                f"Expected appeal_count=2, got {c.appeal_count}"
            assert c.current_day == 5

            # -- Topic: message edited to accepted --
            edited_review = girl.chat_state.get_message(
                KOK_GROUP_ID, appeal_review_msg_id,
            )
            assert edited_review.text == AppealTemplates.topic_appeal_accepted(
                2, AppealTemplates.MAX_APPEALS,
            )

            # -- Topic icon → 💊 --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_ACTIVE)

            # -- Girl: "last chance" warning --
            girl_msgs = girl.get_bot_messages()
            accepted_msgs = [
                m for m in girl_msgs
                if m.text and m.text == AppealTemplates.appeal_accepted(2)
            ]
            assert len(accepted_msgs) >= 1, \
                "Girl should receive appeal_accepted(2) message"
            # Verify it contains "last chance" warning
            assert "последняя возможность" in accepted_msgs[0].text, \
                "Second appeal acceptance should warn about last chance"

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 4: Next day — girl sends on-time video → day 6
            # ══════════════════════════════════════════════════════════
            with freeze_time(NEXT_DAY_VIDEO_TIME):
                await girl.send_video_note("video_day6")

            # -- DB: day advanced --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 6, f"Expected day 6, got {c.current_day}"
            assert c.status.value == "active"

            # -- DB: intake_log for day 6 --
            log6 = await intake_log_repo.get_by_course_and_day(course.id, 6)
            assert log6 is not None
            assert log6.video_file_id == "video_day6"
            assert log6.status == "taken"

            # -- Girl: approved text --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg.text == VideoTemplates.approved(6, TOTAL_DAYS)

            # -- Topic: video_note + approved (5 total: 1 worker + 2 appeal + 2 video) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 5

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 5: Worker 2h removal AGAIN (appeal_count=2 ≥ MAX_APPEALS)
            # ══════════════════════════════════════════════════════════
            with freeze_time(WORKER_TIME_DAY3):
                await removal_2h.run(
                    bot=girl.bot,
                    redis=mock_redis,
                    settings=worker_settings,
                    course_repository=course_repo,
                    user_repository=user_repo,
                    manager_repository=manager_repo,
                    intake_log_repository=intake_log_repo,
                )

            # -- DB: refused permanently --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused", \
                f"Expected refused, got {c.status.value}"
            assert c.appeal_count == 2, "appeal_count unchanged by worker"
            assert c.current_day == 6

            # -- Girl: removal message WITHOUT appeal button --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == WorkerTemplates.removal_no_video("Test Manager")
            assert not girl_msg.has_inline_keyboard(), \
                "NO appeal button when appeal_count=2 >= MAX_APPEALS=2"

            # -- Topic: new removal text (6 total: 5 prev + 1 new) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 6, \
                f"Expected 6 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[5].text == WorkerTemplates.topic_removal_no_video()

            # -- Topic icon → ❗️ + CLOSED --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED)
            assert topic.is_closed, \
                "Topic should be closed after final removal"

            # ══════════════════════════════════════════════════════════
            # STEP 6: Verify finality — no appeal possible
            # ══════════════════════════════════════════════════════════

            # -- DB: refused, appeal_count=2 (= MAX_APPEALS) --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused"
            assert c.appeal_count == AppealTemplates.MAX_APPEALS, \
                f"Expected {AppealTemplates.MAX_APPEALS}, got {c.appeal_count}"
            remaining = AppealTemplates.MAX_APPEALS - c.appeal_count
            assert remaining == 0, "No appeals remaining"

            # -- Girl's last removal message has NO buttons --
            girl_msg = girl.get_last_bot_message()
            assert not girl_msg.has_inline_keyboard(), \
                "Final removal: no appeal button"

            # -- Topic closed with ❗️ icon --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic.is_closed
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED)