"""Scenario: 3 strikes across 3 days via strike_30min worker → removal.

Tests business rules in one end-to-end flow:
1. Day 1: Girl doesn't send video → strike_30min fires → strike 1 + warning
2. Day 2: Girl still doesn't send → strike_30min fires → strike 2 + warning
3. Day 3: Girl still doesn't send → strike_30min fires → strike 3 → REMOVAL
4. Course refused, topic closed, appeal button sent to girl

Key: tests the full 3-strike removal path via workers (not handlers).
Workers bypass Dishka, take explicit parameters.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time
from redis.asyncio import Redis
from supabase import AsyncClient

from config import Settings
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.user_repository import UserRepository
from services.gemini_service import GeminiService
from services.video_service import BASE_MAX_STRIKES, VideoService
from templates import VideoTemplates, WorkerTemplates
from tests.conftest import create_test_course, create_test_manager, create_test_user
from tests.mock_server import MockTelegramBot
from tests.mock_server.chat_state import ForumTopic
from tests.scenarios.conftest import (
    KOK_GROUP_ID,
    KOK_GENERAL_TOPIC_ID,
    create_scenario_dispatcher,
)
from utils.time import TASHKENT_TZ
from workers.tasks import strike_30min

# ── Constants ─────────────────────────────────────────────────────────────

GIRL_TG_ID = 555555
MANAGER_TG_ID = 999999
TOPIC_ID = 42
INTAKE_TIME = time(10, 0)  # 10:00 Tashkent
TOTAL_DAYS = 21

BASE_DATE = datetime(2025, 1, 15, tzinfo=TASHKENT_TZ).date()

# Worker fires exactly 30 min after intake each day
DAY1_STRIKE_TIME = datetime(2025, 1, 15, 10, 30, tzinfo=TASHKENT_TZ)
DAY2_STRIKE_TIME = datetime(2025, 1, 16, 10, 30, tzinfo=TASHKENT_TZ)
DAY3_STRIKE_TIME = datetime(2025, 1, 17, 10, 30, tzinfo=TASHKENT_TZ)

# Topic icon for refused course
TOPIC_ICON_REFUSED = strike_30min.TOPIC_ICON_REFUSED


class TestStrikeWorkerScenario:
    """3 strikes across 3 days → removal by worker."""

    @pytest.fixture
    def mock_redis(self) -> Redis:
        """Mock Redis for worker dedup (was_sent=False each day, mark_sent=OK)."""
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
            name="Ivanova Dasha",
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
        video_service = VideoService(course_repo, intake_log_repo)

        max_strikes = BASE_MAX_STRIKES  # 3 (no appeals)

        # GeminiService not needed (no video processing in this scenario)
        gemini_mock = AsyncMock(spec=GeminiService)
        dp = await create_scenario_dispatcher(supabase, gemini_mock)

        # Worker needs its own settings mock
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
                    name="Ivanova Dasha",
                )
            )

            # ══════════════════════════════════════════════════════════
            # DAY 1: strike_30min fires → strike 1/3 → warning
            # ══════════════════════════════════════════════════════════
            with freeze_time(DAY1_STRIKE_TIME):
                await strike_30min.run(
                    bot=girl.bot,
                    redis=mock_redis,
                    settings=worker_settings,
                    course_repository=course_repo,
                    user_repository=user_repo,
                    manager_repository=manager_repo,
                    intake_log_repository=intake_log_repo,
                    video_service=video_service,
                )

            # -- DB: strike recorded, course still active --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "active", \
                f"Expected active after strike 1, got {c.status.value}"
            assert c.late_count == 1, f"Expected late_count=1, got {c.late_count}"
            assert c.current_day == 5, "Day should NOT change (no video sent)"
            assert len(c.late_dates) == 1, \
                f"Expected 1 late_date, got {len(c.late_dates)}"

            # -- Girl: strike warning message --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == WorkerTemplates.strike_warning(1, max_strikes)

            # -- Topic: late warning --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 1, \
                f"Expected 1 topic msg after day 1, got {len(topic_msgs)}"
            assert topic_msgs[0].text == VideoTemplates.topic_late_warning(
                1, max_strikes,
            )

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # DAY 2: strike_30min fires → strike 2/3 → warning
            # ══════════════════════════════════════════════════════════
            with freeze_time(DAY2_STRIKE_TIME):
                await strike_30min.run(
                    bot=girl.bot,
                    redis=mock_redis,
                    settings=worker_settings,
                    course_repository=course_repo,
                    user_repository=user_repo,
                    manager_repository=manager_repo,
                    intake_log_repository=intake_log_repo,
                    video_service=video_service,
                )

            # -- DB: strike 2 recorded, course still active --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "active", \
                f"Expected active after strike 2, got {c.status.value}"
            assert c.late_count == 2, f"Expected late_count=2, got {c.late_count}"
            assert c.current_day == 5, "Day should NOT change"
            assert len(c.late_dates) == 2, \
                f"Expected 2 late_dates, got {len(c.late_dates)}"

            # -- Girl: strike warning 2/3 --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == WorkerTemplates.strike_warning(2, max_strikes)

            # -- Topic: 2 late warnings total --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 2, \
                f"Expected 2 topic msgs after day 2, got {len(topic_msgs)}"
            assert topic_msgs[1].text == VideoTemplates.topic_late_warning(
                2, max_strikes,
            )

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # DAY 3: strike_30min fires → strike 3/3 → REMOVAL
            # ══════════════════════════════════════════════════════════
            with freeze_time(DAY3_STRIKE_TIME):
                await strike_30min.run(
                    bot=girl.bot,
                    redis=mock_redis,
                    settings=worker_settings,
                    course_repository=course_repo,
                    user_repository=user_repo,
                    manager_repository=manager_repo,
                    intake_log_repository=intake_log_repo,
                    video_service=video_service,
                )

            # -- DB: course REFUSED --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused", \
                f"Expected refused after strike 3, got {c.status.value}"
            assert c.late_count == 3, f"Expected late_count=3, got {c.late_count}"
            assert c.current_day == 5, "Day unchanged"
            assert len(c.late_dates) == 3, \
                f"Expected 3 late_dates, got {len(c.late_dates)}"

            # -- Girl: removal message with appeal button --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            dates_str = VideoTemplates.format_late_dates(c.late_dates)
            assert VideoTemplates.private_late_removed(
                dates_str, "Test Manager",
            ) in girl_msg.text
            assert girl_msg.has_inline_keyboard(), \
                "Girl should see appeal button (appeal_count=0 < MAX_APPEALS)"
            appeal_cb = girl_msg.get_button_callback_data("Апелляция")
            assert appeal_cb is not None, "Appeal button not found"

            # -- Topic: removal text --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            # 2 warnings + 1 removal = 3
            assert len(topic_msgs) == 3, \
                f"Expected 3 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[2].text == VideoTemplates.topic_late_removed(dates_str)

            # -- Topic icon → ❗️ + CLOSED --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED)
            assert topic.is_closed, "Topic should be closed after removal"

            # -- General topic: removal notification --
            general_msgs = girl.get_thread_messages(
                KOK_GROUP_ID, KOK_GENERAL_TOPIC_ID,
            )
            assert len(general_msgs) >= 1, \
                "General topic should receive removal notification"
            assert general_msgs[-1].text == VideoTemplates.general_late_removed(
                "Ivanova Dasha", TOPIC_ID, KOK_GROUP_ID,
            )

            # ══════════════════════════════════════════════════════════
            # VERIFY: Dynamic threshold (3 + appeal_count = 3)
            # ══════════════════════════════════════════════════════════
            assert max_strikes == 3
            assert c.appeal_count == 0, "No appeals in this scenario"
            assert c.late_count >= max_strikes, \
                "late_count should be >= max_strikes for removal"
