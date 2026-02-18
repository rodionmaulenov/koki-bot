"""Tests for workers/tasks/appeal_deadline.py — appeal deadline auto-refuse.

Key logic tested:
- _calculate_appeal_deadline() pure function: today/tomorrow, midnight crossing, fallback
- Two-pass Redis: 1st run stores deadline + continue, 2nd run checks + processes
- refuse_if_appeal (NOT refuse_if_active), new_appeal_count = appeal_count + 1
- Girl notification WITHOUT reply_markup (no appeal button)
- redis.delete(deadline_key) on both refused=True and refused=False
"""
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramForbiddenError

from models.course import Course
from models.enums import CourseStatus
from templates import WorkerTemplates
from utils.time import TASHKENT_TZ
from workers.tasks.appeal_deadline import (
    DEADLINE_HOURS_BEFORE,
    DEADLINE_KEY_TTL,
    REMINDER_TYPE,
    TOPIC_ICON_REFUSED,
    _calculate_appeal_deadline,
    run,
)

from .conftest import GENERAL_TOPIC_ID, JUN_15, KOK_GROUP_ID, make_manager, make_settings, make_user

_PATCH = "workers.tasks.appeal_deadline"

# Stored deadline in the past (already expired relative to JUN_15=14:00)
_STORED_PAST = datetime(2025, 6, 15, 10, 0, tzinfo=TASHKENT_TZ).isoformat()
# Stored deadline in the future
_STORED_FUTURE = datetime(2025, 6, 16, 10, 0, tzinfo=TASHKENT_TZ).isoformat()


def _course(
    course_id: int = 1, user_id: int = 100,
    intake_time: time | None = time(12, 0),
    appeal_count: int = 0,
) -> Course:
    return Course(
        id=course_id, user_id=user_id, status=CourseStatus.APPEAL,
        intake_time=intake_time, appeal_count=appeal_count,
        created_at=JUN_15,
    )


def _redis(stored: str | None = None) -> AsyncMock:
    """Redis mock with .get/.set/.delete support."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=stored)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    return r


def _patches(was_sent_rv=False):
    """Common patches: get_tashkent_now, was_sent, mark_sent."""
    return (
        patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15),
        patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=was_sent_rv),
        patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock),
    )


# =============================================================================
# _calculate_appeal_deadline pure function
# =============================================================================


class TestCalculateAppealDeadline:

    def test_no_intake_time_fallback_24h(self):
        """intake_time=None → now + 24 hours."""
        course = _course(intake_time=None)
        result = _calculate_appeal_deadline(JUN_15, course)
        assert result == JUN_15 + timedelta(hours=24)

    def test_today_deadline_before_now(self):
        """now=10:00, intake=14:00 → today_deadline=12:00 (today)."""
        now = datetime(2025, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)
        course = _course(intake_time=time(14, 0))
        result = _calculate_appeal_deadline(now, course)
        expected = datetime(2025, 6, 15, 12, 0, tzinfo=TASHKENT_TZ)
        assert result == expected
        assert DEADLINE_HOURS_BEFORE == 2

    def test_today_deadline_passed_returns_tomorrow(self):
        """now=14:00, intake=14:00 → today_deadline=12:00 (passed) → tomorrow 12:00."""
        course = _course(intake_time=time(14, 0))
        result = _calculate_appeal_deadline(JUN_15, course)
        expected = datetime(2025, 6, 16, 12, 0, tzinfo=TASHKENT_TZ)
        assert result == expected

    def test_boundary_now_equals_today_deadline(self):
        """now == today_deadline → NOT < → returns tomorrow."""
        now = datetime(2025, 6, 15, 12, 0, tzinfo=TASHKENT_TZ)
        course = _course(intake_time=time(14, 0))
        # today_deadline = 14:00 - 2h = 12:00 = now
        result = _calculate_appeal_deadline(now, course)
        expected = datetime(2025, 6, 16, 12, 0, tzinfo=TASHKENT_TZ)
        assert result == expected

    def test_early_intake_crosses_midnight(self):
        """intake=01:00 → today_deadline = yesterday 23:00 → always tomorrow."""
        now = datetime(2025, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)
        course = _course(intake_time=time(1, 0))
        result = _calculate_appeal_deadline(now, course)
        # tomorrow 01:00 - 2h = today 23:00
        expected = datetime(2025, 6, 15, 23, 0, tzinfo=TASHKENT_TZ)
        assert result == expected


# =============================================================================
# run() tests
# =============================================================================


class TestRun:

    # ── Skip / dedup ──────────────────────────────────────────────────

    async def test_no_appeal_courses_does_nothing(self):
        """Empty appeal courses → no actions."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        course_repo.get_appeal_courses = AsyncMock(return_value=[])

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, _redis(), make_settings(), course_repo,
                      AsyncMock(), AsyncMock())

        bot.send_message.assert_not_called()

    async def test_dedup_skips(self):
        """was_sent=True → skip, redis.get not called."""
        redis = _redis()
        course_repo = AsyncMock()
        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])

        p1, p2, p3 = _patches(was_sent_rv=True)
        with p1, p2, p3:
            await run(AsyncMock(), redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock())

        redis.get.assert_not_called()

    # ── First run — store deadline ────────────────────────────────────

    async def test_first_run_stores_deadline_and_continues(self):
        """No stored deadline → calculate, redis.set, NO refuse."""
        redis = _redis(stored=None)
        course_repo = AsyncMock()
        course_repo.get_appeal_courses = AsyncMock(return_value=[_course(course_id=5)])

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(AsyncMock(), redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock())

        redis.set.assert_called_once()
        course_repo.refuse_if_appeal.assert_not_called()
        mock_mark.assert_not_called()

    async def test_first_run_stores_with_correct_ttl(self):
        """redis.set called with ex=DEADLINE_KEY_TTL (259200 = 3 days)."""
        redis = _redis(stored=None)
        course_repo = AsyncMock()
        course_repo.get_appeal_courses = AsyncMock(return_value=[_course(course_id=5)])

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(AsyncMock(), redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock())

        call_kwargs = redis.set.call_args
        assert call_kwargs.args[0] == "appeal_deadline:5"
        assert call_kwargs.kwargs["ex"] == DEADLINE_KEY_TTL
        assert DEADLINE_KEY_TTL == 86400 * 3

    async def test_first_run_no_intake_time_uses_fallback(self):
        """intake_time=None → stores (now + 24h).isoformat()."""
        redis = _redis(stored=None)
        course_repo = AsyncMock()
        course_repo.get_appeal_courses = AsyncMock(
            return_value=[_course(intake_time=None)],
        )

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(AsyncMock(), redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock())

        stored_value = redis.set.call_args.args[1]
        expected = (JUN_15 + timedelta(hours=24)).isoformat()
        assert stored_value == expected

    # ── Deadline not passed ───────────────────────────────────────────

    async def test_deadline_not_passed_skips(self):
        """Stored deadline in future → skip."""
        redis = _redis(stored=_STORED_FUTURE)
        course_repo = AsyncMock()
        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(AsyncMock(), redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock())

        course_repo.refuse_if_appeal.assert_not_called()
        mock_mark.assert_not_called()

    async def test_deadline_exactly_at_now_skips(self):
        """Stored deadline == now → skip (<= not <)."""
        stored_now = JUN_15.isoformat()
        redis = _redis(stored=stored_now)
        course_repo = AsyncMock()
        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(AsyncMock(), redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock())

        course_repo.refuse_if_appeal.assert_not_called()
        mock_mark.assert_not_called()

    # ── Happy path ────────────────────────────────────────────────────

    async def test_happy_path_refuses_marks_sent_deletes_key_notifies(self):
        """Expired → refuse_if_appeal + mark_sent + redis.delete + girl msg."""
        bot = AsyncMock()
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(
            return_value=[_course(course_id=5, appeal_count=0)],
        )
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo)

        course_repo.refuse_if_appeal.assert_called_once_with(5, 1)
        mock_mark.assert_called_once_with(redis, 5, REMINDER_TYPE)
        assert REMINDER_TYPE == "appeal_expired"
        redis.delete.assert_called_once_with("appeal_deadline:5")

        girl_call = bot.send_message.call_args_list[0]
        assert girl_call.kwargs["chat_id"] == 555000
        assert girl_call.kwargs["text"] == WorkerTemplates.removal_appeal_expired("Aliya")

    async def test_new_appeal_count_incremented(self):
        """appeal_count=1 → refuse_if_appeal(id, 2)."""
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(
            return_value=[_course(course_id=9, appeal_count=1)],
        )
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(AsyncMock(), redis, make_settings(), course_repo,
                      user_repo, manager_repo)

        course_repo.refuse_if_appeal.assert_called_once_with(9, 2)

    # ── Race condition ────────────────────────────────────────────────

    async def test_refuse_race_condition_marks_sent_deletes_key_skips(self):
        """refused=False → mark_sent + redis.delete + no notifications."""
        bot = AsyncMock()
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(
            return_value=[_course(course_id=42)],
        )
        course_repo.refuse_if_appeal = AsyncMock(return_value=False)

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(bot, redis, make_settings(), course_repo,
                      AsyncMock(), AsyncMock())

        mock_mark.assert_called_once_with(redis, 42, REMINDER_TYPE)
        redis.delete.assert_called_once_with("appeal_deadline:42")
        bot.send_message.assert_not_called()

    # ── Notifications ─────────────────────────────────────────────────

    async def test_user_not_found_skips(self):
        """user=None → no notifications."""
        bot = AsyncMock()
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, AsyncMock())

        bot.send_message.assert_not_called()

    async def test_manager_not_found_fallback(self):
        """manager=None → text contains 'менеджер'."""
        bot = AsyncMock()
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user())
        manager_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo)

        girl_text = bot.send_message.call_args_list[0].kwargs["text"]
        assert girl_text == WorkerTemplates.removal_appeal_expired("менеджер")

    async def test_no_telegram_id_skips_girl(self):
        """telegram_id=None → only topic+general (2 calls)."""
        bot = AsyncMock()
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(telegram_id=None, topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo)

        assert bot.send_message.call_count == 2
        for call in bot.send_message.call_args_list:
            assert call.kwargs["chat_id"] == KOK_GROUP_ID

    async def test_girl_no_reply_markup(self):
        """Appeal expired: girl msg has NO reply_markup (unlike other workers)."""
        bot = AsyncMock()
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo)

        girl_call = bot.send_message.call_args_list[0]
        assert "reply_markup" not in girl_call.kwargs

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
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo)

        assert bot.send_message.call_count == 3
        bot.edit_forum_topic.assert_called_once()
        bot.close_forum_topic.assert_called_once()

    # ── Topic ─────────────────────────────────────────────────────────

    async def test_topic_message_icon_close(self):
        """topic_id → message + icon + close with correct args."""
        bot = AsyncMock()
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo)

        topic_call = bot.send_message.call_args_list[1]
        assert topic_call.kwargs["chat_id"] == KOK_GROUP_ID
        assert topic_call.kwargs["message_thread_id"] == 999
        assert topic_call.kwargs["text"] == WorkerTemplates.topic_appeal_expired()

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
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo)

        bot.edit_forum_topic.assert_not_called()
        bot.close_forum_topic.assert_not_called()

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
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=999))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(), course_repo,
                      user_repo, manager_repo)

        bot.edit_forum_topic.assert_called_once()
        bot.close_forum_topic.assert_called_once()

    # ── General topic ─────────────────────────────────────────────────

    async def test_general_topic_with_thread_id(self):
        """kok_general_topic_id=42 → message_thread_id in kwargs."""
        bot = AsyncMock()
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(general_topic_id=GENERAL_TOPIC_ID),
                      course_repo, user_repo, manager_repo)

        general_call = bot.send_message.call_args_list[-1]
        assert general_call.kwargs["message_thread_id"] == GENERAL_TOPIC_ID
        expected = WorkerTemplates.general_appeal_expired("Aliya", "Ivanova", None, KOK_GROUP_ID)
        assert general_call.kwargs["text"] == expected

    async def test_general_topic_without_thread_id(self):
        """kok_general_topic_id=0 → no message_thread_id."""
        bot = AsyncMock()
        redis = _redis(stored=_STORED_PAST)
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        manager_repo = AsyncMock()

        course_repo.get_appeal_courses = AsyncMock(return_value=[_course()])
        course_repo.refuse_if_appeal = AsyncMock(return_value=True)
        user_repo.get_by_id = AsyncMock(return_value=make_user(topic_id=None))
        manager_repo.get_by_id = AsyncMock(return_value=make_manager())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, redis, make_settings(general_topic_id=0),
                      course_repo, user_repo, manager_repo)

        general_call = bot.send_message.call_args_list[-1]
        assert "message_thread_id" not in general_call.kwargs
