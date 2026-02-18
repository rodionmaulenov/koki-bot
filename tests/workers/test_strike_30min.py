"""Tests for workers/tasks/strike_30min.py — strike 30min after intake.

Key logic tested:
- Skip: dedup, video already sent, already late today
- record_late exception → no mark_sent (retry on next run)
- Warning path (not final strike): strike_warning to girl + topic warning
- Removal path (final strike): refuse + girl msg with dates + appeal button + topic + general
- User edge cases: not found / no telegram_id × is_removal / is_warning
- Boundary: late_count == max_strikes → is_removal=True (>= not >)
"""
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramForbiddenError

from models.course import Course
from models.enums import CourseStatus
from templates import AppealTemplates, VideoTemplates, WorkerTemplates
from workers.tasks.strike_30min import REMINDER_TYPE, TOPIC_ICON_REFUSED, run

from .conftest import GENERAL_TOPIC_ID, JUN_15, KOK_GROUP_ID, make_manager, make_settings, make_user

_PATCH = "workers.tasks.strike_30min"

_LATE_DATES_3 = [
    "2025-06-13T14:30:00+05:00",
    "2025-06-14T12:30:00+05:00",
    "2025-06-15T12:30:00+05:00",
]


def _course(
    course_id: int = 1, user_id: int = 100,
    current_day: int = 5, appeal_count: int = 0,
    intake_time: time | None = time(12, 0),
    late_dates: list[str] | None = None,
    late_count: int = 0,
) -> Course:
    return Course(
        id=course_id, user_id=user_id, status=CourseStatus.ACTIVE,
        current_day=current_day, appeal_count=appeal_count,
        intake_time=intake_time, late_dates=late_dates or [],
        late_count=late_count, created_at=JUN_15,
    )


def _video_service(
    late_count: int = 2,
    late_dates: list[str] | None = None,
    max_strikes: int = 3,
) -> AsyncMock:
    vs = AsyncMock()
    vs.record_late = AsyncMock(
        return_value=(late_count, late_dates or _LATE_DATES_3[:late_count]),
    )
    vs.get_max_strikes = MagicMock(return_value=max_strikes)
    return vs


def _patches(was_sent_rv=False):
    """Common patches for time, dedup."""
    return (
        patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15),
        patch(f"{_PATCH}.calculate_time_range_after", return_value=(time(11, 28), time(11, 38))),
        patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=was_sent_rv),
        patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock),
    )


# =============================================================================
# TESTS
# =============================================================================


class TestRun:

    # ── Skip / dedup ──────────────────────────────────────────────────

    async def test_no_courses_does_nothing(self):
        """Empty course list → no actions."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[])

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), AsyncMock(), _video_service())

        bot.send_message.assert_not_called()

    async def test_dedup_skips(self):
        """was_sent=True → skip, has_log_today not called."""
        intake_log_repo = AsyncMock()
        course_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])

        p1, p2, p3, p4 = _patches(was_sent_rv=True)
        with p1, p2, p3, p4:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo, _video_service())

        intake_log_repo.has_log_today.assert_not_called()

    async def test_video_already_sent_skips(self):
        """has_log_today=True → skip, record_late not called."""
        vs = _video_service()
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=True)

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo, vs)

        vs.record_late.assert_not_called()

    async def test_next_day_is_current_day_plus_1(self):
        """current_day=5 → has_log_today called with day=6."""
        intake_log_repo = AsyncMock()
        intake_log_repo.has_log_today = AsyncMock(return_value=True)
        course_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(
            return_value=[_course(course_id=7, current_day=5)],
        )

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo, _video_service())

        intake_log_repo.has_log_today.assert_called_once_with(7, 6)

    async def test_already_late_today_marks_sent_and_skips(self):
        """today in late_dates → mark_sent called, record_late NOT called."""
        vs = _video_service()
        redis = AsyncMock()
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()
        course = _course(course_id=42, late_dates=["2025-06-15T12:30:00+05:00"])
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[course])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4 as mock_mark:
            await run(AsyncMock(), redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo, vs)

        mock_mark.assert_called_once_with(redis, 42, REMINDER_TYPE)
        vs.record_late.assert_not_called()

    # ── record_late exception ─────────────────────────────────────────

    async def test_record_late_exception_no_mark_sent(self):
        """record_late raises → continue without mark_sent (retry next run)."""
        vs = _video_service()
        vs.record_late = AsyncMock(side_effect=RuntimeError("db error"))
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4 as mock_mark:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo, vs)

        mock_mark.assert_not_called()

    # ── Warning path (not final strike) ──────────────────────────────

    async def test_warning_sends_correct_text(self):
        """late_count=2, max=3 → strike_warning(2, 3) sent to girl."""
        bot = AsyncMock()
        redis = AsyncMock()
        vs = _video_service(late_count=2, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        bot.send_message.assert_called_once()
        call = bot.send_message.call_args
        assert call.kwargs["chat_id"] == 555000
        assert call.kwargs["text"] == WorkerTemplates.strike_warning(2, 3)
        mock_mark.assert_called_once_with(redis, 1, REMINDER_TYPE)

    async def test_warning_sends_topic_message(self):
        """Warning path + topic_id → topic_late_warning sent."""
        bot = AsyncMock()
        vs = _video_service(late_count=2, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        assert bot.send_message.call_count == 2
        topic_call = bot.send_message.call_args_list[1]
        assert topic_call.kwargs["chat_id"] == KOK_GROUP_ID
        assert topic_call.kwargs["message_thread_id"] == 999
        assert topic_call.kwargs["text"] == VideoTemplates.topic_late_warning(2, 3)

    async def test_warning_no_topic_id_skips_topic(self):
        """Warning path + topic_id=None → only 1 send_message (girl only)."""
        bot = AsyncMock()
        vs = _video_service(late_count=2, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        bot.send_message.assert_called_once()

    async def test_warning_telegram_forbidden_no_crash(self):
        """TelegramForbiddenError on warning → no crash."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(
            side_effect=TelegramForbiddenError(method=MagicMock(), message="Forbidden"),
        )
        vs = _video_service(late_count=2, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        # No crash — test passes if we reach here

    async def test_warning_generic_exception_no_crash(self):
        """Generic exception on warning → no crash."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(side_effect=RuntimeError("network"))
        vs = _video_service(late_count=2, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        # No crash — test passes if we reach here

    # ── Removal path (final strike) ──────────────────────────────────

    async def test_removal_refuses_and_notifies_girl(self):
        """late=3, max=3 → refuse + girl msg with dates + mark_sent."""
        bot = AsyncMock()
        redis = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
        with p1, p2, p3, p4 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo, vs)

        course_repo.refuse_if_active.assert_called_once_with(1, removal_reason="max_strikes")
        dates_str = VideoTemplates.format_late_dates(_LATE_DATES_3)
        girl_call = bot.send_message.call_args_list[0]
        assert girl_call.kwargs["chat_id"] == 555000
        assert girl_call.kwargs["text"] == VideoTemplates.private_late_removed(
            dates_str, "Aliya",
        )
        mock_mark.assert_called_once_with(redis, 1, REMINDER_TYPE)
        assert REMINDER_TYPE == "strike"

    async def test_removal_appeal_button_eligible(self):
        """appeal_count=0 < MAX_APPEALS → markup is not None."""
        bot = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
                      user_repo, manager_repo, intake_log_repo, vs)

        girl_markup = bot.send_message.call_args_list[0].kwargs["reply_markup"]
        assert girl_markup is not None

    async def test_removal_no_appeal_button_max_reached(self):
        """appeal_count >= MAX_APPEALS → reply_markup=None."""
        bot = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
                      user_repo, manager_repo, intake_log_repo, vs)

        girl_markup = bot.send_message.call_args_list[0].kwargs["reply_markup"]
        assert girl_markup is None

    async def test_removal_topic_message_icon_close(self):
        """Removal path with topic_id → message + icon + close."""
        bot = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
                      user_repo, manager_repo, intake_log_repo, vs)

        dates_str = VideoTemplates.format_late_dates(_LATE_DATES_3)
        topic_call = bot.send_message.call_args_list[1]
        assert topic_call.kwargs["chat_id"] == KOK_GROUP_ID
        assert topic_call.kwargs["message_thread_id"] == 999
        assert topic_call.kwargs["text"] == VideoTemplates.topic_late_removed(dates_str)

        bot.edit_forum_topic.assert_called_once_with(
            chat_id=KOK_GROUP_ID,
            message_thread_id=999,
            icon_custom_emoji_id=str(TOPIC_ICON_REFUSED),
        )
        bot.close_forum_topic.assert_called_once_with(
            chat_id=KOK_GROUP_ID,
            message_thread_id=999,
        )

    async def test_removal_no_topic_id_skips_topic(self):
        """Removal path + topic_id=None → no icon/close."""
        bot = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
                      user_repo, manager_repo, intake_log_repo, vs)

        bot.edit_forum_topic.assert_not_called()
        bot.close_forum_topic.assert_not_called()

    async def test_removal_general_topic_with_thread_id(self):
        """kok_general_topic_id=42 → general msg has message_thread_id."""
        bot = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
                      course_repo, user_repo, manager_repo, intake_log_repo, vs)

        general_call = bot.send_message.call_args_list[-1]
        assert general_call.kwargs["message_thread_id"] == GENERAL_TOPIC_ID
        expected = VideoTemplates.general_late_removed("Ivanova", None, KOK_GROUP_ID)
        assert general_call.kwargs["text"] == expected

    async def test_removal_general_topic_without_thread_id(self):
        """kok_general_topic_id=0 → no message_thread_id."""
        bot = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
                      course_repo, user_repo, manager_repo, intake_log_repo, vs)

        general_call = bot.send_message.call_args_list[-1]
        assert "message_thread_id" not in general_call.kwargs

    async def test_removal_manager_not_found_fallback(self):
        """manager=None → text contains 'менеджер'."""
        bot = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
                      user_repo, manager_repo, intake_log_repo, vs)

        dates_str = VideoTemplates.format_late_dates(_LATE_DATES_3)
        girl_text = bot.send_message.call_args_list[0].kwargs["text"]
        assert girl_text == VideoTemplates.private_late_removed(dates_str, "менеджер")

    async def test_removal_refuse_race_condition_skips(self):
        """refuse_if_active=False → skip all notifications."""
        bot = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        course_repo.refuse_if_active = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=make_user())

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        bot.send_message.assert_not_called()

    async def test_removal_girl_forbidden_continues_topic(self):
        """TelegramForbiddenError on girl → topic actions still run."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(
            side_effect=[
                TelegramForbiddenError(method=MagicMock(), message="Forbidden"),
                AsyncMock(),  # topic message
                AsyncMock(),  # general message
            ],
        )
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
                      user_repo, manager_repo, intake_log_repo, vs)

        assert bot.send_message.call_count == 3
        bot.edit_forum_topic.assert_called_once()
        bot.close_forum_topic.assert_called_once()

    # ── User edge cases ──────────────────────────────────────────────

    async def test_user_not_found_refuses_on_removal(self):
        """user=None + is_removal → refuse_if_active called."""
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(
            return_value=[_course(course_id=42)],
        )
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        course_repo.refuse_if_active.assert_called_once_with(42, removal_reason="max_strikes")

    async def test_user_no_telegram_id_refuses_on_removal(self):
        """telegram_id=None + is_removal → refuse_if_active called."""
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=make_user(telegram_id=None))

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        course_repo.refuse_if_active.assert_called_once_with(1, removal_reason="max_strikes")

    async def test_user_not_found_no_refuse_on_warning(self):
        """user=None + is_warning → refuse_if_active NOT called."""
        vs = _video_service(late_count=2, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        course_repo.refuse_if_active.assert_not_called()

    async def test_user_no_telegram_id_no_refuse_on_warning(self):
        """telegram_id=None + is_warning → refuse_if_active NOT called."""
        vs = _video_service(late_count=2, max_strikes=3)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        intake_log_repo.has_log_today = AsyncMock(return_value=False)
        user_repo.get_by_id = AsyncMock(return_value=make_user(telegram_id=None))

        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo, vs)

        course_repo.refuse_if_active.assert_not_called()

    # ── Boundary ─────────────────────────────────────────────────────

    async def test_boundary_late_equals_max_is_removal(self):
        """late_count=3 == max_strikes=3 → is_removal (>= not >)."""
        bot = AsyncMock()
        vs = _video_service(late_count=3, late_dates=_LATE_DATES_3, max_strikes=3)
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
                      user_repo, manager_repo, intake_log_repo, vs)

        # Proves removal path: refuse called + removal text (not warning)
        course_repo.refuse_if_active.assert_called_once()
        dates_str = VideoTemplates.format_late_dates(_LATE_DATES_3)
        girl_text = bot.send_message.call_args_list[0].kwargs["text"]
        assert girl_text == VideoTemplates.private_late_removed(dates_str, "Aliya")
