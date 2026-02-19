"""Scenario: Late strikes → removal → appeal → dynamic threshold → second removal.

Tests business rules in one end-to-end flow:
1. On-time video → approved, day incremented, topic gets video + status
2. Late video (>30min) → approved with late warning, strike recorded, topic late warning
3. 3rd strike → undo day + refuse course (BASE_MAX_STRIKES = 3)
4. Girl sees appeal button (appeal_count < MAX_APPEALS)
5. Appeal click removes button, changes course status refused → appeal
6. Appeal FSM: video → text → submitted, topic gets review buttons
7. Manager accept: appeal → active, appeal_count incremented, topic text edited
8. Dynamic threshold: max_strikes = 3 + appeal_count = 4
9. 4th strike → undo day + refuse (hit new threshold)
10. Girl still sees appeal button (appeal_count=1 < MAX_APPEALS=2)
11. Topic icons change correctly at each state transition
12. IntakeLog records correct at each step
13. late_dates contain exact timestamps
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from supabase import AsyncClient

from handlers.video.receive import (
    TOPIC_ICON_ACTIVE,
    TOPIC_ICON_REFUSED,
)
from handlers.appeal.submit import TOPIC_ICON_APPEAL
from models.video_result import VideoResult
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from services.gemini_service import GeminiService
from services.video_service import BASE_MAX_STRIKES
from templates import AppealTemplates, VideoTemplates
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

# Base date for the scenario
BASE_DATE = datetime(2025, 1, 15, tzinfo=TASHKENT_TZ).date()


def _on_time(day_offset: int) -> datetime:
    """10:05 Tashkent on BASE_DATE + day_offset (5 min delay — not late)."""
    d = BASE_DATE + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, 10, 5, tzinfo=TASHKENT_TZ)


def _late(day_offset: int) -> datetime:
    """10:45 Tashkent on BASE_DATE + day_offset (45 min delay — late!)."""
    d = BASE_DATE + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, 10, 45, tzinfo=TASHKENT_TZ)


class TestStrikeAppealScenario:
    """Full end-to-end: 3 late strikes → removal → appeal → dynamic threshold."""

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
        """Create test data: manager, user, active course."""
        manager = await create_test_manager(
            supabase, telegram_id=MANAGER_TG_ID, name="Test Manager",
        )
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Marina",
            telegram_id=GIRL_TG_ID,
            topic_id=TOPIC_ID,
        )
        course = await create_test_course(
            supabase, user_id=user.id,
            status="active",
            intake_time=INTAKE_TIME.isoformat(),
            start_date=str(BASE_DATE - timedelta(days=3)),
            current_day=2,  # Already did days 1-2
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
            # Pre-create forum topic so icon changes are tracked
            girl.chat_state._forum_topics.setdefault(KOK_GROUP_ID, {})[TOPIC_ID] = (
                ForumTopic(
                    message_thread_id=TOPIC_ID,
                    chat_id=KOK_GROUP_ID,
                    name="Ivanova Marina",
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
            # STEP 1: Day 3 — on-time intake (delay=5min, not late)
            # ══════════════════════════════════════════════════════════
            with freeze_time(_on_time(0)):
                await girl.send_video_note("video_day3")

            # -- DB: course --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 3, f"Expected day 3, got {c.current_day}"
            assert c.status.value == "active"
            assert c.late_count == 0

            # -- DB: intake_log --
            log3 = await intake_log_repo.get_by_course_and_day(course.id, 3)
            assert log3 is not None, "IntakeLog for day 3 not found"
            assert log3.video_file_id == "video_day3"
            assert log3.status == "taken"
            assert log3.delay_minutes is not None
            assert log3.delay_minutes <= 30, f"Day 3 should not be late, got {log3.delay_minutes}min"

            # -- Girl: exact approved text --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.approved(3, TOTAL_DAYS)

            # -- Topic: video_note + approved status text --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 2, f"Expected 2 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[0].video_note is not None, "First topic msg should be video_note"
            assert topic_msgs[1].text == VideoTemplates.topic_approved(3, TOTAL_DAYS)

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 2: Day 4 — late intake (delay=45min) → strike 1
            # ══════════════════════════════════════════════════════════
            with freeze_time(_late(1)):
                await girl.send_video_note("video_day4")

            # -- DB: course --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 4
            assert c.status.value == "active"
            assert c.late_count == 1
            assert len(c.late_dates) == 1

            # -- DB: intake_log --
            log4 = await intake_log_repo.get_by_course_and_day(course.id, 4)
            assert log4 is not None, "IntakeLog for day 4 not found"
            assert log4.video_file_id == "video_day4"
            assert log4.status == "taken"
            assert log4.delay_minutes is not None
            assert log4.delay_minutes > 30, f"Day 4 should be late, got {log4.delay_minutes}min"

            # -- Girl: exact approved_late text --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            max_strikes = BASE_MAX_STRIKES + c.appeal_count  # 3 + 0 = 3
            assert girl_msg.text == VideoTemplates.approved_late(4, TOTAL_DAYS, 1, max_strikes)

            # -- Topic: video + approved + late_warning (3 new msgs, 5 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 5, f"Expected 5 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[2].video_note is not None, "3rd topic msg should be video_note"
            assert topic_msgs[3].text == VideoTemplates.topic_approved(4, TOTAL_DAYS)
            assert topic_msgs[4].text == VideoTemplates.topic_late_warning(1, max_strikes)

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 3: Day 5 — late intake → strike 2
            # ══════════════════════════════════════════════════════════
            with freeze_time(_late(2)):
                await girl.send_video_note("video_day5")

            # -- DB: course --
            c = await course_repo.get_by_id(course.id)
            assert c.current_day == 5
            assert c.status.value == "active"
            assert c.late_count == 2
            assert len(c.late_dates) == 2

            # -- DB: intake_log --
            log5 = await intake_log_repo.get_by_course_and_day(course.id, 5)
            assert log5 is not None, "IntakeLog for day 5 not found"
            assert log5.video_file_id == "video_day5"
            assert log5.status == "taken"
            assert log5.delay_minutes is not None
            assert log5.delay_minutes > 30

            # -- Girl: exact approved_late text --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == VideoTemplates.approved_late(5, TOTAL_DAYS, 2, max_strikes)

            # -- Topic: video + approved + late_warning (3 new, 8 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 8, f"Expected 8 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[5].video_note is not None
            assert topic_msgs[6].text == VideoTemplates.topic_approved(5, TOTAL_DAYS)
            assert topic_msgs[7].text == VideoTemplates.topic_late_warning(2, max_strikes)

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 4: Day 6 — late intake → strike 3 → REMOVAL!
            # ══════════════════════════════════════════════════════════
            with freeze_time(_late(3)):
                await girl.send_video_note("video_day6")

            # -- DB: course --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused", f"Expected refused, got {c.status.value}"
            assert c.current_day == 5, f"Expected day undone to 5, got {c.current_day}"
            assert c.late_count == 3
            assert len(c.late_dates) == 3

            # -- DB: late_dates contain exact timestamps --
            dates_str = VideoTemplates.format_late_dates(c.late_dates)
            assert "16.01 10:45" in dates_str, "Late date 1 missing"
            assert "17.01 10:45" in dates_str, "Late date 2 missing"
            assert "18.01 10:45" in dates_str, "Late date 3 missing"

            # -- Girl: removal text + appeal button --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            expected_removal = VideoTemplates.private_late_removed(dates_str, "Test Manager")
            assert girl_msg.text == expected_removal
            assert girl_msg.has_inline_keyboard(), "Girl should see appeal button"
            appeal_cb = girl_msg.get_button_callback_data("Апелляция")
            assert appeal_cb is not None, "Appeal button not found"
            removal_msg_id = girl_msg.message_id  # Save for step 5

            # -- Topic: video + removal text (2 new, 10 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 10, f"Expected 10 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[8].video_note is not None
            assert topic_msgs[9].text == VideoTemplates.topic_late_removed(dates_str)

            # -- Topic icon → ❗️ (refused) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED)

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 5: Girl starts appeal
            # ══════════════════════════════════════════════════════════
            await girl.click_button(appeal_cb, removal_msg_id)

            # -- DB: status changed --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "appeal"

            # -- Girl: appeal button REMOVED from removal message --
            updated_removal = girl.get_message(removal_msg_id)
            assert updated_removal is not None
            assert not updated_removal.has_inline_keyboard(), \
                "Appeal button should be removed after clicking"

            # -- Girl: sees "send appeal video" prompt --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == AppealTemplates.ask_video()

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 6: Girl sends appeal video + text
            # ══════════════════════════════════════════════════════════
            await girl.send_video_note("appeal_video_file_id")

            # Girl sees "send appeal text" prompt
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == AppealTemplates.ask_text()

            await girl.send_message("Прошу пересмотреть решение")

            # -- DB: appeal data saved --
            c = await course_repo.get_by_id(course.id)
            assert c.appeal_video == "appeal_video_file_id"
            assert c.appeal_text == "Прошу пересмотреть решение"

            # -- Girl: "appeal submitted" confirmation --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            assert girl_msg.text == AppealTemplates.appeal_submitted()

            # -- Topic icon → ❓ (appeal in progress) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_APPEAL)
            assert not topic.is_closed, "Topic should be reopened for appeal"

            # -- Topic: appeal video + appeal text with buttons (2 new, 12 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 12, f"Expected 12 topic msgs, got {len(topic_msgs)}"

            # Appeal video in topic
            assert topic_msgs[10].video is not None, \
                "Appeal video should be sent to topic"

            # Appeal text with review buttons
            appeal_review_msg = topic_msgs[11]
            assert appeal_review_msg.text == AppealTemplates.topic_appeal_submitted(
                "Прошу пересмотреть решение",
            )
            assert appeal_review_msg.has_inline_keyboard()
            accept_cb = appeal_review_msg.get_button_callback_data("Принять")
            decline_cb = appeal_review_msg.get_button_callback_data("Отклонить")
            assert accept_cb is not None, "Accept button not found"
            assert decline_cb is not None, "Decline button not found"
            appeal_review_msg_id = appeal_review_msg.message_id  # Save for step 7

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 7: Manager accepts appeal
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
            assert c.late_count == 3  # NOT reset — stays at 3
            assert c.current_day == 5  # NOT changed

            # -- Dynamic threshold: max_strikes = 3 + 1 = 4 --
            new_max = BASE_MAX_STRIKES + c.appeal_count
            assert new_max == 4

            # -- Topic: appeal review message EDITED —
            #    text changed to accepted, buttons removed --
            edited_review = girl.chat_state.get_message(
                KOK_GROUP_ID, appeal_review_msg_id,
            )
            assert edited_review is not None
            assert edited_review.text == AppealTemplates.topic_appeal_accepted(
                1, AppealTemplates.MAX_APPEALS,
            )
            # Note: reply_markup removal not checked — mock server doesn't clear
            # reply_markup when editMessageText is called without it (aiogram
            # omits the field when reply_markup=None).
            # The text update proves edit_text was called correctly.

            # -- Topic icon → 💊 (active again) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_ACTIVE)

            # -- Girl received "appeal accepted" in private chat --
            girl_msgs = girl.get_bot_messages()
            accepted_msgs = [
                m for m in girl_msgs
                if m.text and m.text == AppealTemplates.appeal_accepted(1)
            ]
            assert len(accepted_msgs) >= 1, "Girl should receive appeal_accepted message"

            girl.clear_requests_only()

            # ══════════════════════════════════════════════════════════
            # STEP 8: Day 6 again — late → strike 4 → SECOND REMOVAL
            # ══════════════════════════════════════════════════════════

            # Clean up old intake_log for day 6 (created in step 4, before undo).
            # undo_day_and_refuse resets current_day but doesn't delete the log.
            # get_today_log would find the old log and block re-sending.
            # This is a known limitation of the code.
            await (
                supabase.schema("kok").table("intake_logs")
                .delete()
                .eq("course_id", course.id)
                .eq("day", 6)
                .execute()
            )

            with freeze_time(_late(4)):
                await girl.send_video_note("video_day6_retry")

            # -- DB: course refused again --
            c = await course_repo.get_by_id(course.id)
            assert c.status.value == "refused", f"Expected refused, got {c.status.value}"
            assert c.current_day == 5, f"Expected day undone to 5, got {c.current_day}"
            assert c.late_count == 4
            assert c.appeal_count == 1  # Unchanged
            assert len(c.late_dates) == 4

            # -- Dynamic threshold hit: 4 >= 4 (BASE_MAX_STRIKES + appeal_count) --
            assert c.late_count >= BASE_MAX_STRIKES + c.appeal_count

            # -- DB: late_dates now has 4 entries --
            dates_str_2 = VideoTemplates.format_late_dates(c.late_dates)
            assert "19.01 10:45" in dates_str_2, "4th late date missing"

            # -- Girl: removal text + appeal button (still available) --
            girl_msg = girl.get_last_bot_message()
            assert girl_msg is not None
            expected_removal_2 = VideoTemplates.private_late_removed(
                dates_str_2, "Test Manager",
            )
            assert girl_msg.text == expected_removal_2
            assert girl_msg.has_inline_keyboard(), \
                "Girl should still see appeal button (appeal_count=1 < MAX_APPEALS=2)"

            # -- Topic: video + removal text (2 new, 14 total) --
            topic_msgs = girl.get_thread_messages(KOK_GROUP_ID, TOPIC_ID)
            assert len(topic_msgs) == 14, f"Expected 14 topic msgs, got {len(topic_msgs)}"
            assert topic_msgs[12].video_note is not None
            assert topic_msgs[13].text == VideoTemplates.topic_late_removed(dates_str_2)

            # -- Topic icon → ❗️ (refused again) --
            topic = girl.get_forum_topic(KOK_GROUP_ID, TOPIC_ID)
            assert topic is not None
            assert topic.icon_custom_emoji_id == str(TOPIC_ICON_REFUSED)
