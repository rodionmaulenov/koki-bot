"""Tests for workers/tasks/removal_2h.py — auto-removal 2h after intake.

Key logic tested:
- Happy path: no video after 2h → refuse course → notify girl + topic + general
- Dedup: was_sent=True → skip
- Video already sent (has_log_today) → skip
- Race condition: refuse_if_active=False → mark_sent + skip
- User not found after refuse → skip notifications
- Manager not found → fallback name "менеджер"
- Appeal button: appeal_count < MAX_APPEALS → button, >= → None
- No telegram_id → skip girl message, topic still sent
- No topic_id → skip topic actions
- General topic: kok_general_topic_id=0 → no message_thread_id
- Error handling: TelegramForbiddenError, generic exceptions
"""
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramForbiddenError

from models.course import Course
from models.enums import CourseStatus
from templates import AppealTemplates, WorkerTemplates
from workers.tasks.removal_2h import REMINDER_TYPE, TOPIC_ICON_REFUSED, run

from .conftest import GENERAL_TOPIC_ID, JUN_15, KOK_GROUP_ID, make_manager, make_settings, make_user

_PATCH = "workers.tasks.removal_2h"


def _course(
    course_id: int = 1, user_id: int = 100,
    current_day: int = 5, appeal_count: int = 0,
    intake_time: time | None = time(12, 0),
    start_date: date = date(2025, 6, 10),
) -> Course:
    return Course(
        id=course_id, user_id=user_id, status=CourseStatus.ACTIVE,
        current_day=current_day, appeal_count=appeal_count,
        intake_time=intake_time, start_date=start_date, created_at=JUN_15,
    )


def _patches(was_sent_rv=False, mark_sent_mock=None):
    """Common patches for get_tashkent_now, calculate_time_range_after, was_sent, mark_sent."""
    return (
        patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15),
        patch(f"{_PATCH}.calculate_time_range_after", return_value=(time(11, 58), time(12, 8))),
        patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=was_sent_rv),
        patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock) if mark_sent_mock is None
        else patch(f"{_PATCH}.mark_sent", mark_sent_mock),
    )


# =============================================================================
# TESTS
# =============================================================================


class TestRun:

    # ── Empty / dedup / skip ────────────────────────────────────────────

    async def test_no_courses_does_nothing(self):
        """Empty course list → no actions."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[])

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), AsyncMock())

        bot.send_message.assert_not_called()

    async def test_dedup_skips_already_sent(self):
        """was_sent=True → skip entire course processing."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])

        p1, p2, p3, p4 = _patches(was_sent_rv=True)
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        intake_log_repo.has_log_today.assert_not_called()
        bot.send_message.assert_not_called()

    async def test_video_already_sent_skips(self):
        """has_log_today=True → don't refuse, don't notify."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=True)

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        course_repo.refuse_if_active.assert_not_called()
        bot.send_message.assert_not_called()

    async def test_expected_day_from_start_date(self):
        """start_date=June 10, now=June 15 → expected_day=6."""
        intake_log_repo = AsyncMock()
        intake_log_repo.has_log_today = AsyncMock(return_value=True)
        course_repo = AsyncMock()
        course = _course(course_id=7, start_date=date(2025, 6, 10))
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[course])

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        intake_log_repo.has_log_today.assert_called_once_with(7, 6)

    async def test_ai_auto_approved_skips_removal(self):
        """AI auto-approved → current_day already advanced, but expected_day still correct."""
        intake_log_repo = AsyncMock()
        intake_log_repo.has_log_today = AsyncMock(return_value=True)
        course_repo = AsyncMock()
        # current_day=6 (AI advanced), but start_date=June 10, now=June 15 → day=6
        course_repo.get_active_in_intake_window = AsyncMock(
            return_value=[_course(current_day=6, start_date=date(2025, 6, 10))],
        )

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        intake_log_repo.has_log_today.assert_called_once_with(1, 6)
        course_repo.refuse_if_active.assert_not_called()

    async def test_midnight_crossing_uses_yesterday(self):
        """Worker runs at 01:35 → intake_date is yesterday → correct day."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        midnight_now = datetime(2025, 6, 16, 1, 35, tzinfo=ZoneInfo("Asia/Tashkent"))
        intake_log_repo = AsyncMock()
        intake_log_repo.has_log_today = AsyncMock(return_value=True)
        course_repo = AsyncMock()
        # start_date=June 10, intake was June 15 (yesterday) → day=6
        course_repo.get_active_in_intake_window = AsyncMock(
            return_value=[_course(current_day=6, start_date=date(2025, 6, 10))],
        )

        patches = (
            patch(f"{_PATCH}.get_tashkent_now", return_value=midnight_now),
            patch(f"{_PATCH}.calculate_time_range_after", return_value=(time(23, 28), time(23, 38))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=False),
            patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        # intake_date = (01:35 - 120min).date() = June 15 → day=6
        intake_log_repo.has_log_today.assert_called_once_with(1, 6)
        course_repo.refuse_if_active.assert_not_called()

    # ── Race condition ──────────────────────────────────────────────────

    async def test_refuse_if_active_false_marks_sent_and_skips(self):
        """refuse_if_active=False (race condition) → mark_sent, no notifications."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course(course_id=42)])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=False)
        redis = AsyncMock()

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        mock_mark.assert_called_once_with(redis, 42, REMINDER_TYPE)
        bot.send_message.assert_not_called()

    # ── Happy path ──────────────────────────────────────────────────────

    async def test_happy_path_refuses_and_notifies_girl(self):
        """Full flow: refuse + send_message to girl with correct text."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        # refuse_if_active called with removal_reason
        course_repo.refuse_if_active.assert_called_once_with(
            1, removal_reason="no_video",
        )

        # Girl gets message
        calls = bot.send_message.call_args_list
        girl_call = calls[0]
        assert girl_call.kwargs["chat_id"] == 555000
        assert "Aliya" in girl_call.kwargs["text"]
        assert girl_call.kwargs["text"] == WorkerTemplates.removal_no_video("Aliya")

        # mark_sent called
        mock_mark.assert_called_once_with(redis, 1, REMINDER_TYPE)
        assert REMINDER_TYPE == "removal_2h"

    async def test_happy_path_sends_topic_message(self):
        """Topic message sent with correct chat_id and thread_id."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        # Find topic send_message call (second call, after girl)
        topic_call = bot.send_message.call_args_list[1]
        assert topic_call.kwargs["chat_id"] == KOK_GROUP_ID
        assert topic_call.kwargs["message_thread_id"] == 999
        assert topic_call.kwargs["text"] == WorkerTemplates.topic_removal_no_video()

    async def test_happy_path_changes_topic_icon(self):
        """edit_forum_topic called with TOPIC_ICON_REFUSED."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        bot.edit_forum_topic.assert_called_once_with(
            chat_id=KOK_GROUP_ID,
            message_thread_id=999,
            icon_custom_emoji_id=str(TOPIC_ICON_REFUSED),
        )

    async def test_happy_path_closes_topic(self):
        """close_forum_topic called."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        bot.close_forum_topic.assert_called_once_with(
            chat_id=KOK_GROUP_ID,
            message_thread_id=999,
        )

    async def test_happy_path_sends_general_topic(self):
        """General topic message with manager_name and girl_name."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(general_topic_id=GENERAL_TOPIC_ID),
                      course_repo, user_repo, manager_repo, intake_log_repo)

        # Last send_message call is general topic (no topic_id → only girl + general)
        general_call = bot.send_message.call_args_list[-1]
        assert general_call.kwargs["chat_id"] == KOK_GROUP_ID
        assert general_call.kwargs["message_thread_id"] == GENERAL_TOPIC_ID
        expected_text = WorkerTemplates.general_removal_no_video("Ivanova", None, KOK_GROUP_ID)
        assert general_call.kwargs["text"] == expected_text

    # ── Manager fallback ────────────────────────────────────────────────

    async def test_manager_not_found_uses_fallback_name(self):
        """manager_repo returns None → text contains 'менеджер'."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        manager_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        girl_text = bot.send_message.call_args_list[0].kwargs["text"]
        assert "менеджер" in girl_text
        assert girl_text == WorkerTemplates.removal_no_video("менеджер")

    # ── Appeal button ───────────────────────────────────────────────────

    async def test_appeal_button_when_eligible(self):
        """appeal_count=0 < MAX_APPEALS → reply_markup is not None."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(
            return_value=[_course(appeal_count=0)],
        )
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        girl_markup = bot.send_message.call_args_list[0].kwargs["reply_markup"]
        assert girl_markup is not None

    async def test_no_appeal_button_when_max_reached(self):
        """appeal_count=2 >= MAX_APPEALS=2 → reply_markup=None."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(
            return_value=[_course(appeal_count=AppealTemplates.MAX_APPEALS)],
        )
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        girl_markup = bot.send_message.call_args_list[0].kwargs["reply_markup"]
        assert girl_markup is None

    # ── No telegram_id / no topic_id ────────────────────────────────────

    async def test_no_telegram_id_skips_girl_message(self):
        """user.telegram_id=None → no girl message, but topic actions still run."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(telegram_id=None, topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        # Topic message + general = 2 calls (no girl message)
        calls = bot.send_message.call_args_list
        for call in calls:
            assert call.kwargs["chat_id"] != 555000
        # Topic actions still happen
        bot.edit_forum_topic.assert_called_once()
        bot.close_forum_topic.assert_called_once()

    async def test_no_topic_id_skips_topic_actions(self):
        """user.topic_id=None → no topic message/icon/close."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        bot.edit_forum_topic.assert_not_called()
        bot.close_forum_topic.assert_not_called()

    # ── General topic without thread_id ─────────────────────────────────

    async def test_general_topic_without_thread_id(self):
        """kok_general_topic_id=0 → send_message WITHOUT message_thread_id."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(general_topic_id=0),
                      course_repo, user_repo, manager_repo, intake_log_repo)

        # General call is last (girl + general = 2, no topic)
        general_call = bot.send_message.call_args_list[-1]
        assert general_call.kwargs["chat_id"] == KOK_GROUP_ID
        assert "message_thread_id" not in general_call.kwargs

    # ── User not found after refuse ─────────────────────────────────────

    async def test_user_not_found_skips_after_refuse(self):
        """refuse=True but user=None → mark_sent called, no notifications."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course(course_id=7)])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo)

        # mark_sent still called (course already refused)
        mock_mark.assert_called_once_with(redis, 7, REMINDER_TYPE)
        bot.send_message.assert_not_called()

    # ── Error handling ──────────────────────────────────────────────────

    async def test_girl_blocked_bot_no_crash(self):
        """TelegramForbiddenError on girl message → no crash, topic still sent."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(
            side_effect=[
                TelegramForbiddenError(method=MagicMock(), message="Forbidden"),
                AsyncMock(),  # topic message
                AsyncMock(),  # general message
            ],
        )
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        # 3 send_message attempts (girl=error, topic, general)
        assert bot.send_message.call_count == 3
        bot.edit_forum_topic.assert_called_once()

    async def test_girl_send_exception_no_crash(self):
        """Generic exception on girl message → no crash, topic still sent."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(
            side_effect=[
                RuntimeError("network"),
                AsyncMock(),  # topic message
                AsyncMock(),  # general message
            ],
        )
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        assert bot.send_message.call_count == 3
        bot.close_forum_topic.assert_called_once()

    async def test_topic_exception_continues_to_icon_and_close(self):
        """Exception on topic send_message → edit_forum_topic and close still called."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(
            side_effect=[
                AsyncMock(),   # girl message OK
                RuntimeError("topic fail"),  # topic message fails
                AsyncMock(),   # general message OK
            ],
        )
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        # Icon and close still attempted despite topic message failure
        bot.edit_forum_topic.assert_called_once()
        bot.close_forum_topic.assert_called_once()
