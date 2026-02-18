"""Tests for workers/tasks/review_deadline.py — review deadline auto-removal.

Key logic tested:
- _review_deadline() pure function: deadline = combine(review_date+1, intake_time) - 2h
- Skip: dedup, course not found/inactive (mark_sent), missing data (NO mark_sent)
- Deadline not passed / exactly at now (boundary <=)
- Happy path: refuse + update_status("missed") + mark_sent + notify
- Race condition: refuse_if_active=False → mark_sent + skip
- Notifications: girl + appeal button + topic + general + error handling
"""
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramForbiddenError

from models.course import Course
from models.enums import CourseStatus
from models.intake_log import IntakeLog
from templates import AppealTemplates, WorkerTemplates
from utils.time import TASHKENT_TZ
from workers.tasks.review_deadline import (
    DEADLINE_HOURS_BEFORE,
    REMINDER_TYPE,
    TOPIC_ICON_REFUSED,
    _review_deadline,
    run,
)

from .conftest import GENERAL_TOPIC_ID, JUN_15, KOK_GROUP_ID, make_manager, make_settings, make_user

_PATCH = "workers.tasks.review_deadline"
_JUN_14_10 = datetime(2025, 6, 14, 10, 0, tzinfo=TASHKENT_TZ)


def _log(
    log_id: int = 1, course_id: int = 1,
    review_started_at: datetime | None = _JUN_14_10,
) -> IntakeLog:
    return IntakeLog(
        id=log_id, course_id=course_id, day=1,
        review_started_at=review_started_at,
        created_at=JUN_15,
    )


def _course(
    course_id: int = 1, user_id: int = 100,
    status: CourseStatus = CourseStatus.ACTIVE,
    intake_time: time | None = time(12, 0),
    appeal_count: int = 0,
) -> Course:
    return Course(
        id=course_id, user_id=user_id, status=status,
        intake_time=intake_time, appeal_count=appeal_count,
        created_at=JUN_15,
    )


def _patches(was_sent_rv=False):
    """Common patches: get_tashkent_now, was_sent, mark_sent."""
    return (
        patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15),
        patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=was_sent_rv),
        patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock),
    )


# =============================================================================
# _review_deadline pure function
# =============================================================================


class TestReviewDeadline:

    def test_standard(self):
        """review June 15 14:00, intake 12:00 → June 16 10:00."""
        review = datetime(2025, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)
        result = _review_deadline(review, time(12, 0))
        expected = datetime(2025, 6, 16, 10, 0, tzinfo=TASHKENT_TZ)
        assert result == expected
        assert DEADLINE_HOURS_BEFORE == 2

    def test_early_intake_crosses_midnight(self):
        """intake 01:00 → deadline crosses back to review day: June 15 23:00."""
        review = datetime(2025, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)
        result = _review_deadline(review, time(1, 0))
        expected = datetime(2025, 6, 15, 23, 0, tzinfo=TASHKENT_TZ)
        assert result == expected

    def test_uses_review_date_not_time(self):
        """Different review times on same day → same deadline."""
        day = datetime(2025, 6, 15, tzinfo=TASHKENT_TZ)
        review_morning = day.replace(hour=8)
        review_evening = day.replace(hour=22)
        intake = time(14, 0)

        assert _review_deadline(review_morning, intake) == _review_deadline(review_evening, intake)
        expected = datetime(2025, 6, 16, 12, 0, tzinfo=TASHKENT_TZ)
        assert _review_deadline(review_morning, intake) == expected


# =============================================================================
# run() tests
# =============================================================================


class TestRun:

    # ── Skip / dedup ──────────────────────────────────────────────────

    async def test_no_pending_logs_does_nothing(self):
        """Empty pending logs → no actions."""
        bot = AsyncMock()
        intake_log_repo = AsyncMock()
        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[])

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(), AsyncMock(),
                      AsyncMock(), AsyncMock(), intake_log_repo)

        bot.send_message.assert_not_called()

    async def test_dedup_skips(self):
        """was_sent=True → skip, course not fetched."""
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()
        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])

        p1, p2, p3 = _patches(was_sent_rv=True)
        with p1, p2, p3:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        course_repo.get_by_id.assert_not_called()

    async def test_course_not_found_marks_sent_and_skips(self):
        """course=None → mark_sent + skip (no retry)."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        log = _log(course_id=42)
        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[log])
        course_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        mock_mark.assert_called_once_with(redis, 42, REMINDER_TYPE)
        bot.send_message.assert_not_called()

    async def test_course_not_active_marks_sent_and_skips(self):
        """status='refused' → mark_sent + skip, refuse NOT called."""
        redis = AsyncMock()
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        log = _log(course_id=7)
        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[log])
        course_repo.get_by_id = AsyncMock(
            return_value=_course(course_id=7, status=CourseStatus.REFUSED),
        )

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(AsyncMock(), redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        mock_mark.assert_called_once_with(redis, 7, REMINDER_TYPE)
        course_repo.refuse_if_active.assert_not_called()

    async def test_missing_review_started_at_skips_no_mark_sent(self):
        """review_started_at=None → skip WITHOUT mark_sent (retry)."""
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        log = _log(review_started_at=None)
        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[log])
        course_repo.get_by_id = AsyncMock(return_value=_course())

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        mock_mark.assert_not_called()

    async def test_missing_intake_time_skips_no_mark_sent(self):
        """intake_time=None → skip WITHOUT mark_sent (retry)."""
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(
            return_value=_course(intake_time=None),
        )

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        mock_mark.assert_not_called()

    async def test_deadline_not_passed_skips(self):
        """now < deadline → skip, no mark_sent."""
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        # review today 10:00 → deadline = June 16 16:00 (18:00 - 2h)
        # now = June 15 14:00 < deadline
        log = _log(review_started_at=datetime(2025, 6, 15, 10, 0, tzinfo=TASHKENT_TZ))
        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[log])
        course_repo.get_by_id = AsyncMock(return_value=_course(intake_time=time(18, 0)))

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        mock_mark.assert_not_called()
        course_repo.refuse_if_active.assert_not_called()

    # ── Boundary ──────────────────────────────────────────────────────

    async def test_deadline_exactly_at_now_skips(self):
        """now == deadline → skip (<= not <)."""
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        # deadline must equal JUN_15 (June 15 14:00)
        # combine(June 15, 16:00) - 2h = June 15 14:00
        # review_date + 1 = June 15 → review June 14
        log = _log(review_started_at=datetime(2025, 6, 14, 10, 0, tzinfo=TASHKENT_TZ))
        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[log])
        course_repo.get_by_id = AsyncMock(return_value=_course(intake_time=time(16, 0)))

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(AsyncMock(), AsyncMock(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        mock_mark.assert_not_called()
        course_repo.refuse_if_active.assert_not_called()

    # ── Happy path ────────────────────────────────────────────────────

    async def test_happy_path_refuses_updates_log_notifies_girl(self):
        """Expired → refuse + update_status('missed') + mark_sent + girl msg."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        log = _log(log_id=77, course_id=5)
        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[log])
        course_repo.get_by_id = AsyncMock(return_value=_course(course_id=5))
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        course_repo.refuse_if_active.assert_called_once_with(5, removal_reason="review_deadline")
        intake_log_repo.update_status.assert_called_once_with(77, "missed")
        mock_mark.assert_called_once_with(redis, 5, REMINDER_TYPE)
        assert REMINDER_TYPE == "review_expired"

        girl_call = bot.send_message.call_args_list[0]
        assert girl_call.kwargs["chat_id"] == 555000
        assert girl_call.kwargs["text"] == WorkerTemplates.removal_review_expired("Aliya")

    # ── Race condition ────────────────────────────────────────────────

    async def test_refuse_race_condition_marks_sent_skips(self):
        """refuse_if_active=False → mark_sent + skip, update_status NOT called."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        log = _log(course_id=42)
        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[log])
        course_repo.get_by_id = AsyncMock(return_value=_course(course_id=42))
        course_repo.refuse_if_active = AsyncMock(return_value=False)

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock(), intake_log_repo)

        mock_mark.assert_called_once_with(redis, 42, REMINDER_TYPE)
        intake_log_repo.update_status.assert_not_called()
        bot.send_message.assert_not_called()

    # ── Notifications ─────────────────────────────────────────────────

    async def test_user_not_found_skips(self):
        """user=None → no notifications."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course())
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, AsyncMock(), intake_log_repo)

        bot.send_message.assert_not_called()

    async def test_manager_not_found_fallback(self):
        """manager=None → text contains 'менеджер'."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course())
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        manager_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        girl_text = bot.send_message.call_args_list[0].kwargs["text"]
        assert girl_text == WorkerTemplates.removal_review_expired("менеджер")

    async def test_no_appeal_button_manager_decision(self):
        """review_deadline = manager decision → no appeal button ever."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course(appeal_count=0))
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        girl_call = bot.send_message.call_args_list[0]
        assert "reply_markup" not in girl_call.kwargs or girl_call.kwargs["reply_markup"] is None

    async def test_no_telegram_id_skips_girl(self):
        """telegram_id=None → no girl msg, only topic+general (2 calls)."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course())
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(telegram_id=None, topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        # Only 2 calls: topic msg + general msg (no girl msg)
        assert bot.send_message.call_count == 2
        for call in bot.send_message.call_args_list:
            assert call.kwargs["chat_id"] == KOK_GROUP_ID
        bot.edit_forum_topic.assert_called_once()
        bot.close_forum_topic.assert_called_once()

    async def test_topic_message_icon_close(self):
        """topic_id → message + icon + close."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course())
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        topic_call = bot.send_message.call_args_list[1]
        assert topic_call.kwargs["chat_id"] == KOK_GROUP_ID
        assert topic_call.kwargs["message_thread_id"] == 999
        assert topic_call.kwargs["text"] == WorkerTemplates.topic_removal_review_expired()

        bot.edit_forum_topic.assert_called_once_with(
            chat_id=KOK_GROUP_ID,
            message_thread_id=999,
            icon_custom_emoji_id=str(TOPIC_ICON_REFUSED),
        )
        bot.close_forum_topic.assert_called_once_with(
            chat_id=KOK_GROUP_ID,
            message_thread_id=999,
        )

    async def test_no_topic_id_skips_topic(self):
        """topic_id=None → no icon/close."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course())
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        bot.edit_forum_topic.assert_not_called()
        bot.close_forum_topic.assert_not_called()

    async def test_general_topic_with_thread_id(self):
        """kok_general_topic_id=42 → message_thread_id in kwargs."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course())
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(general_topic_id=GENERAL_TOPIC_ID),
                      course_repo, user_repo, manager_repo, intake_log_repo)

        general_call = bot.send_message.call_args_list[-1]
        assert general_call.kwargs["message_thread_id"] == GENERAL_TOPIC_ID
        expected = WorkerTemplates.general_removal_review_expired("Aliya", "Ivanova", None, KOK_GROUP_ID)
        assert general_call.kwargs["text"] == expected

    async def test_general_topic_without_thread_id(self):
        """kok_general_topic_id=0 → no message_thread_id."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course())
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(general_topic_id=0),
                      course_repo, user_repo, manager_repo, intake_log_repo)

        general_call = bot.send_message.call_args_list[-1]
        assert "message_thread_id" not in general_call.kwargs

    # ── Error handling ────────────────────────────────────────────────

    async def test_girl_forbidden_continues_topic(self):
        """TelegramForbiddenError on girl → topic actions still run."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(
            side_effect=[
                TelegramForbiddenError(method=MagicMock(), message="Forbidden"),
                AsyncMock(),  # topic
                AsyncMock(),  # general
            ],
        )
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course())
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        assert bot.send_message.call_count == 3
        bot.edit_forum_topic.assert_called_once()
        bot.close_forum_topic.assert_called_once()

    async def test_topic_exception_continues_icon_close(self):
        """Exception on topic msg → icon + close still called."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(
            side_effect=[
                AsyncMock(),   # girl OK
                RuntimeError("topic fail"),  # topic fails
                AsyncMock(),   # general OK
            ],
        )
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()
        intake_log_repo = AsyncMock()

        intake_log_repo.get_pending_reviews_with_start = AsyncMock(return_value=[_log()])
        course_repo.get_by_id = AsyncMock(return_value=_course())
        course_repo.refuse_if_active = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), make_settings(), course_repo,
                      user_repo, manager_repo, intake_log_repo)

        bot.edit_forum_topic.assert_called_once()
        bot.close_forum_topic.assert_called_once()
