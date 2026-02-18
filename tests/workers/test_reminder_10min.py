"""Tests for workers/tasks/reminder_10min.py — 10-minute reminder before intake.

Key logic tested:
- Happy path: course found → user has telegram_id → send reminder → mark_sent
- Dedup: was_sent=True → skip
- No user / no telegram_id → skip
- intake_time=None → empty string in message text
- TelegramForbiddenError → no crash, no mark_sent
- Generic exception → no crash, no mark_sent
- Multiple courses: mix of skip/send in one run
"""
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramForbiddenError

from models.course import Course
from models.enums import CourseStatus
from models.user import User
from templates import WorkerTemplates
from utils.time import TASHKENT_TZ
from workers.tasks.reminder_10min import REMINDER_TYPE, run

_PATCH = "workers.tasks.reminder_10min"
_JUN_15 = datetime(2025, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)


def _course(course_id: int = 1, user_id: int = 100, intake_time: time | None = time(14, 30)) -> Course:
    return Course(
        id=course_id, user_id=user_id, status=CourseStatus.ACTIVE,
        intake_time=intake_time, created_at=_JUN_15,
    )


def _user(user_id: int = 100, telegram_id: int | None = 555000) -> User:
    return User(
        id=user_id, telegram_id=telegram_id, name="Test",
        manager_id=1, created_at=_JUN_15,
    )


# =============================================================================
# TESTS
# =============================================================================


class TestRun:
    async def test_no_courses_does_nothing(self):
        """Empty course list → no send_message calls."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[])

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
        ):
            await run(bot, redis, course_repo, user_repo)

        bot.send_message.assert_not_called()

    async def test_happy_path_sends_reminder(self):
        """Course + user with telegram_id → send_message with correct chat_id."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course = _course()
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[course])
        user_repo.get_by_id = AsyncMock(return_value=_user())

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=False),
            patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock) as mock_mark,
        ):
            await run(bot, redis, course_repo, user_repo)

        bot.send_message.assert_called_once_with(
            chat_id=555000,
            text=WorkerTemplates.reminder_10min("14:30"),
        )
        mock_mark.assert_called_once()

    async def test_message_text_contains_intake_time(self):
        """Intake time 14:30 → message text includes '14:30'."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(
            return_value=[_course(intake_time=time(14, 30))],
        )
        user_repo.get_by_id = AsyncMock(return_value=_user())

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=False),
            patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock),
        ):
            await run(bot, redis, course_repo, user_repo)

        text = bot.send_message.call_args.kwargs["text"]
        assert "14:30" in text

    async def test_intake_time_none_empty_string(self):
        """course.intake_time=None → empty string in message text."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(
            return_value=[_course(intake_time=None)],
        )
        user_repo.get_by_id = AsyncMock(return_value=_user())

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=False),
            patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock),
        ):
            await run(bot, redis, course_repo, user_repo)

        text = bot.send_message.call_args.kwargs["text"]
        assert text == WorkerTemplates.reminder_10min("")

    async def test_dedup_skips_already_sent(self):
        """was_sent=True → send_message not called."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=True),
        ):
            await run(bot, redis, course_repo, user_repo)

        bot.send_message.assert_not_called()
        user_repo.get_by_id.assert_not_called()

    async def test_mark_sent_after_success(self):
        """After successful send → mark_sent called with (redis, course.id, '10min')."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course = _course(course_id=42)
        course_repo.get_active_in_intake_window = AsyncMock(return_value=[course])
        user_repo.get_by_id = AsyncMock(return_value=_user())

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=False),
            patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock) as mock_mark,
        ):
            await run(bot, redis, course_repo, user_repo)

        mock_mark.assert_called_once_with(redis, 42, REMINDER_TYPE)
        assert REMINDER_TYPE == "10min"

    async def test_user_not_found_skips(self):
        """get_by_id returns None → send_message not called."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        user_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=False),
        ):
            await run(bot, redis, course_repo, user_repo)

        bot.send_message.assert_not_called()

    async def test_user_no_telegram_id_skips(self):
        """user.telegram_id=None → send_message not called."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        user_repo.get_by_id = AsyncMock(return_value=_user(telegram_id=None))

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=False),
        ):
            await run(bot, redis, course_repo, user_repo)

        bot.send_message.assert_not_called()

    async def test_telegram_forbidden_no_crash(self):
        """TelegramForbiddenError → no crash, mark_sent NOT called."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(
            side_effect=TelegramForbiddenError(method=MagicMock(), message="Forbidden"),
        )
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        user_repo.get_by_id = AsyncMock(return_value=_user())

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=False),
            patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock) as mock_mark,
        ):
            await run(bot, redis, course_repo, user_repo)

        mock_mark.assert_not_called()

    async def test_generic_exception_no_crash(self):
        """Generic exception in send_message → no crash, mark_sent NOT called."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(side_effect=RuntimeError("network"))
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_active_in_intake_window = AsyncMock(return_value=[_course()])
        user_repo.get_by_id = AsyncMock(return_value=_user())

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=False),
            patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock) as mock_mark,
        ):
            await run(bot, redis, course_repo, user_repo)

        mock_mark.assert_not_called()

    async def test_multiple_courses_processes_each(self):
        """3 courses: 1 dedup, 1 no user, 1 ok → send_message called once."""
        bot = AsyncMock()
        redis = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        c_dedup = _course(course_id=1, user_id=100)
        c_no_user = _course(course_id=2, user_id=200)
        c_ok = _course(course_id=3, user_id=300)
        course_repo.get_active_in_intake_window = AsyncMock(
            return_value=[c_dedup, c_no_user, c_ok],
        )
        user_repo.get_by_id = AsyncMock(side_effect=lambda uid: {
            200: None,
            300: _user(user_id=300, telegram_id=777000),
        }.get(uid))

        async def _was_sent_side_effect(_redis, course_id, _type):
            return course_id == 1  # only first is dedup'd

        with (
            patch(f"{_PATCH}.get_tashkent_now", return_value=_JUN_15),
            patch(f"{_PATCH}.calculate_time_range_before", return_value=(time(14, 18), time(14, 28))),
            patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, side_effect=_was_sent_side_effect),
            patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock) as mock_mark,
        ):
            await run(bot, redis, course_repo, user_repo)

        bot.send_message.assert_called_once_with(
            chat_id=777000,
            text=WorkerTemplates.reminder_10min("14:30"),
        )
        mock_mark.assert_called_once_with(redis, 3, REMINDER_TYPE)
