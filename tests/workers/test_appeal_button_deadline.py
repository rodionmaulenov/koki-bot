"""Tests for workers/tasks/appeal_button_deadline.py — appeal button expiry notification.

Key logic tested:
- Finds refused courses with expired appeal_deadline
- Redis dedup (was_sent/mark_sent)
- Sends notification to girl
- TelegramForbiddenError → suppress
- No user / no telegram_id → skip
"""
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramForbiddenError

from models.course import Course
from models.enums import CourseStatus
from templates import WorkerTemplates
from utils.time import TASHKENT_TZ
from workers.tasks.appeal_button_deadline import REMINDER_TYPE, run

from .conftest import JUN_15, make_user

_PATCH = "workers.tasks.appeal_button_deadline"

# Deadline in the past (expired)
_EXPIRED_DEADLINE = datetime(2025, 6, 15, 10, 0, tzinfo=TASHKENT_TZ)


def _course(
    course_id: int = 1, user_id: int = 100,
    intake_time: time | None = time(12, 0),
    appeal_deadline: datetime | None = _EXPIRED_DEADLINE,
) -> Course:
    return Course(
        id=course_id, user_id=user_id, status=CourseStatus.REFUSED,
        intake_time=intake_time, appeal_deadline=appeal_deadline,
        created_at=JUN_15,
    )


def _patches(was_sent_rv=False):
    return (
        patch(f"{_PATCH}.get_tashkent_now", return_value=JUN_15),
        patch(f"{_PATCH}.was_sent", new_callable=AsyncMock, return_value=was_sent_rv),
        patch(f"{_PATCH}.mark_sent", new_callable=AsyncMock),
    )


class TestRun:

    async def test_no_expired_courses_does_nothing(self):
        """Empty list → no actions."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        course_repo.get_refused_with_expired_appeal = AsyncMock(return_value=[])

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), course_repo, AsyncMock())

        bot.send_message.assert_not_called()

    async def test_dedup_skips(self):
        """was_sent=True → skip."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        course_repo.get_refused_with_expired_appeal = AsyncMock(
            return_value=[_course()],
        )

        p1, p2, p3 = _patches(was_sent_rv=True)
        with p1, p2, p3 as mock_mark:
            await run(bot, AsyncMock(), course_repo, AsyncMock())

        mock_mark.assert_not_called()
        bot.send_message.assert_not_called()

    async def test_happy_path_sends_notification(self):
        """Expired → mark_sent + send notification to girl."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_refused_with_expired_appeal = AsyncMock(
            return_value=[_course(course_id=5)],
        )
        user_repo.get_by_id = AsyncMock(return_value=make_user())

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(bot, AsyncMock(), course_repo, user_repo)

        mock_mark.assert_called_once()
        bot.send_message.assert_called_once()
        call_kwargs = bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 555000
        assert call_kwargs["text"] == WorkerTemplates.appeal_button_expired()

    async def test_reminder_type_correct(self):
        assert REMINDER_TYPE == "appeal_button_expired"

    async def test_user_not_found_skips(self):
        """user=None → no notification."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_refused_with_expired_appeal = AsyncMock(
            return_value=[_course()],
        )
        user_repo.get_by_id = AsyncMock(return_value=None)

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), course_repo, user_repo)

        bot.send_message.assert_not_called()

    async def test_no_telegram_id_skips(self):
        """telegram_id=None → no notification."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_refused_with_expired_appeal = AsyncMock(
            return_value=[_course()],
        )
        user_repo.get_by_id = AsyncMock(
            return_value=make_user(telegram_id=None),
        )

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), course_repo, user_repo)

        bot.send_message.assert_not_called()

    async def test_girl_forbidden_suppressed(self):
        """TelegramForbiddenError → no crash."""
        bot = AsyncMock()
        bot.send_message = AsyncMock(
            side_effect=TelegramForbiddenError(
                method=MagicMock(), message="Forbidden",
            ),
        )
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_refused_with_expired_appeal = AsyncMock(
            return_value=[_course()],
        )
        user_repo.get_by_id = AsyncMock(return_value=make_user())

        p1, p2, p3 = _patches()
        with p1, p2, p3 as mock_mark:
            await run(bot, AsyncMock(), course_repo, user_repo)

        mock_mark.assert_called_once()

    async def test_no_reply_markup(self):
        """Notification has NO reply_markup (no appeal button)."""
        bot = AsyncMock()
        course_repo = AsyncMock()
        user_repo = AsyncMock()

        course_repo.get_refused_with_expired_appeal = AsyncMock(
            return_value=[_course()],
        )
        user_repo.get_by_id = AsyncMock(return_value=make_user())

        p1, p2, p3 = _patches()
        with p1, p2, p3:
            await run(bot, AsyncMock(), course_repo, user_repo)

        call_kwargs = bot.send_message.call_args.kwargs
        assert "reply_markup" not in call_kwargs
