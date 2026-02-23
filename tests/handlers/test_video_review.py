"""Tests for handlers/video/review.py — 67 tests, 100% branch coverage."""
from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any
from unittest.mock import ANY

from callbacks.video import VideoAction, VideoCallback
from handlers.video.review import (
    TOPIC_ICON_ACTIVE,
    TOPIC_ICON_COMPLETED,
    TOPIC_ICON_REFUSED,
    TOPIC_ICON_RESHOOT,
)
from models.course import Course
from models.enums import CourseStatus
from models.intake_log import IntakeLog
from models.manager import Manager
from models.user import User as KokUser
from templates import VideoTemplates
from tests.handlers.conftest import (
    KOK_GENERAL_TOPIC_ID,
    KOK_GROUP_ID,
    MockHolder,
    create_test_dispatcher,
)
from tests.mock_server import MockTelegramBot
from tests.mock_server.tracker import TrackedRequest
from utils.time import TASHKENT_TZ

# ── Constants ─────────────────────────────────────────────────────────────

BOT_ID = 1234567890
USER_ID = 123456789
MANAGER_TG_ID = 999999
TOPIC_ID = 42
LOG_ID = 100
COURSE_ID = 10
PRIVATE_MSG_ID = 50
CALLBACK_MSG_ID = 1

_S_GROUP = str(KOK_GROUP_ID)
_S_GENERAL = str(KOK_GENERAL_TOPIC_ID)

LATE_DATES = [
    "2025-01-13T10:31:00+05:00",
    "2025-01-14T10:40:00+05:00",
    "2025-01-15T11:00:00+05:00",
]

DEADLINE = datetime(2025, 1, 16, 8, 0, 0, tzinfo=TASHKENT_TZ)
DEADLINE_STR = "16.01 08:00"


# ── Factories ─────────────────────────────────────────────────────────────


def _user(**ov: Any) -> KokUser:
    d: dict[str, Any] = dict(
        id=1, telegram_id=USER_ID, name="Test Girl",
        manager_id=1, topic_id=TOPIC_ID,
        created_at=datetime(2025, 1, 1, tzinfo=TASHKENT_TZ),
    )
    d.update(ov)
    return KokUser(**d)


def _course(**ov: Any) -> Course:
    d: dict[str, Any] = dict(
        id=COURSE_ID, user_id=1, status=CourseStatus.ACTIVE,
        intake_time=time(10, 0), current_day=5, total_days=21,
        late_count=0, appeal_count=0, late_dates=[],
        created_at=datetime(2025, 1, 1, tzinfo=TASHKENT_TZ),
    )
    d.update(ov)
    return Course(**d)


def _log(**ov: Any) -> IntakeLog:
    d: dict[str, Any] = dict(
        id=LOG_ID, course_id=COURSE_ID, day=6, status="pending_review",
        delay_minutes=5, video_file_id="vid", confidence=0.95,
        verified_by="gemini", private_message_id=PRIVATE_MSG_ID,
        created_at=datetime(2025, 1, 15, tzinfo=TASHKENT_TZ),
    )
    d.update(ov)
    return IntakeLog(**d)


def _manager(**ov: Any) -> Manager:
    d: dict[str, Any] = dict(
        id=1, telegram_id=MANAGER_TG_ID, name="Test Manager",
        is_active=True, created_at=datetime(2025, 1, 1, tzinfo=TASHKENT_TZ),
    )
    d.update(ov)
    return Manager(**d)


# ── Callback data ─────────────────────────────────────────────────────────


def _confirm(log_id: int = LOG_ID) -> str:
    return VideoCallback(action=VideoAction.CONFIRM, log_id=log_id).pack()


def _reject(log_id: int = LOG_ID) -> str:
    return VideoCallback(action=VideoAction.REJECT, log_id=log_id).pack()


def _reshoot(log_id: int = LOG_ID) -> str:
    return VideoCallback(action=VideoAction.RESHOOT, log_id=log_id).pack()


# ── Mock setup ────────────────────────────────────────────────────────────


def _setup_confirm(m: MockHolder, **kw: Any) -> None:
    """Configure mocks for on_confirm handler."""
    m.intake_log_repo.get_by_id.return_value = kw.get("log", _log())
    m.course_repo.get_by_id.return_value = kw.get("course", _course())
    m.user_repo.get_by_id.return_value = kw.get("user", _user())
    m.manager_repo.get_by_id.return_value = kw.get("manager", _manager())
    m.video_service.get_max_strikes.return_value = kw.get("max_strikes", 3)
    m.video_service.record_late.return_value = kw.get("late_result", (0, []))


def _setup_reject(m: MockHolder, **kw: Any) -> None:
    """Configure mocks for on_reject handler."""
    m.intake_log_repo.get_by_id.return_value = kw.get("log", _log())
    m.course_repo.get_by_id.return_value = kw.get("course", _course())
    m.user_repo.get_by_id.return_value = kw.get("user", _user())
    m.manager_repo.get_by_id.return_value = kw.get("manager", _manager())


def _setup_reshoot(m: MockHolder, **kw: Any) -> None:
    """Configure mocks for on_reshoot handler."""
    m.intake_log_repo.get_by_id.return_value = kw.get("log", _log())
    m.course_repo.get_by_id.return_value = kw.get("course", _course())
    m.user_repo.get_by_id.return_value = kw.get("user", _user())
    m.video_service.request_reshoot.return_value = kw.get("deadline", DEADLINE)


# ── Tracker helpers ───────────────────────────────────────────────────────


def _edits(bot: MockTelegramBot) -> list[TrackedRequest]:
    """All editMessageText requests."""
    return bot._server.tracker.get_requests_by_method("editMessageText")


def _private_edits(bot: MockTelegramBot) -> list[TrackedRequest]:
    """editMessageText for private message (by PRIVATE_MSG_ID)."""
    return [r for r in _edits(bot)
            if str(r.data.get("message_id")) == str(PRIVATE_MSG_ID)]


def _private_sends(bot: MockTelegramBot) -> list[TrackedRequest]:
    """sendMessage to girl's private chat (by USER_ID)."""
    reqs = bot._server.tracker.get_requests_by_method("sendMessage")
    return [r for r in reqs if str(r.data.get("chat_id")) == str(USER_ID)]


def _callback_edits(bot: MockTelegramBot) -> list[TrackedRequest]:
    """editMessageText for callback message (by CALLBACK_MSG_ID)."""
    return [r for r in _edits(bot)
            if str(r.data.get("message_id")) == str(CALLBACK_MSG_ID)]


def _forum_edits(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("editForumTopic")


def _forum_closes(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("closeForumTopic")


def _group_sends(
    bot: MockTelegramBot, topic_id: int | None = None,
) -> list[TrackedRequest]:
    """sendMessage to group, optionally filtered by thread_id."""
    reqs = bot._server.tracker.get_requests_by_method("sendMessage")
    out = []
    for r in reqs:
        if str(r.data.get("chat_id")) == _S_GROUP:
            if topic_id is None or str(r.data.get("message_thread_id")) == str(topic_id):
                out.append(r)
    return out


def _answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("answerCallbackQuery")


def _is_alert(r: TrackedRequest) -> bool:
    return str(r.data.get("show_alert", "")).lower() in ("true", "1")


def _alert_answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return [r for r in _answers(bot) if _is_alert(r)]


def _has_appeal_button(data: dict[str, Any]) -> bool:
    """Check if reply_markup contains 'Апелляция' button."""
    markup = data.get("reply_markup")
    if not markup:
        return False
    if isinstance(markup, str):
        markup = json.loads(markup)
    for row in markup.get("inline_keyboard", []):
        for btn in row:
            if "Апелляция" in btn.get("text", ""):
                return True
    return False


def _seed(bot: MockTelegramBot) -> None:
    """Pre-add callback + private messages so edits work on mock server."""
    bot.chat_state.add_message(
        chat_id=bot.chat_id, from_user_id=BOT_ID, is_bot=True,
        text="pending review", message_id=CALLBACK_MSG_ID,
    )
    bot.chat_state.add_message(
        chat_id=USER_ID, from_user_id=BOT_ID, is_bot=True,
        text="pending review", message_id=PRIVATE_MSG_ID,
    )


def _fail(bot: MockTelegramBot, method_name: str) -> None:
    """Make a specific Telegram API method return 500."""
    orig = bot._server._route_method

    def patched(method: str, data: dict[str, Any]) -> dict[str, Any]:
        if method == method_name:
            return {"ok": False, "error_code": 500, "description": "Mock error"}
        return orig(method, data)

    bot._server._route_method = patched  # type: ignore[assignment]


# ═════════════════════════════════════════════════════════════════════════
# on_confirm (lines 33-215)
# ═════════════════════════════════════════════════════════════════════════


class TestOnConfirmGuards:
    """Guard clauses: intake_log not found / wrong status / course not found."""

    async def test_log_not_found(self, mocks: MockHolder):
        mocks.intake_log_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1
            assert VideoTemplates.review_already_handled() in _answers(bot)[0].data.get("text", "")
            mocks.video_service.confirm_intake.assert_not_called()

    async def test_log_wrong_status(self, mocks: MockHolder):
        """status='taken' (not pending_review) → already handled."""
        mocks.intake_log_repo.get_by_id.return_value = _log(status="taken")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1
            mocks.video_service.confirm_intake.assert_not_called()

    async def test_course_not_found(self, mocks: MockHolder):
        mocks.intake_log_repo.get_by_id.return_value = _log()
        mocks.course_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1
            assert "курс не найден" in _answers(bot)[0].data.get("text", "")
            mocks.video_service.confirm_intake.assert_not_called()


class TestOnConfirmHappyPath:
    """Simple confirm: not late, not completion, not day 1."""

    async def test_confirm_intake_called(self, mocks: MockHolder):
        _setup_confirm(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            mocks.video_service.confirm_intake.assert_called_once_with(LOG_ID, COURSE_ID, 6)

    async def test_topic_message_confirmed(self, mocks: MockHolder):
        _setup_confirm(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            cb = _callback_edits(bot)
            assert len(cb) >= 1
            assert VideoTemplates.topic_confirmed(6, 21) == cb[0].data.get("text")

    async def test_private_message_confirmed(self, mocks: MockHolder):
        _setup_confirm(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert len(pe) == 1
            assert VideoTemplates.private_confirmed(6, 21) == pe[0].data.get("text")

    async def test_callback_answered(self, mocks: MockHolder):
        _setup_confirm(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1

    async def test_first_day_icon_active(self, mocks: MockHolder):
        """day=1, not late → icon changes to TOPIC_ICON_ACTIVE."""
        _setup_confirm(mocks, log=_log(day=1))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            fe = _forum_edits(bot)
            assert len(fe) == 1
            assert fe[0].data.get("icon_custom_emoji_id") == str(TOPIC_ICON_ACTIVE)


class TestOnConfirmLateBoundary:
    """Late threshold: delay_minutes > 30 (strict greater-than)."""

    async def test_delay_none_not_late(self, mocks: MockHolder):
        _setup_confirm(mocks, log=_log(delay_minutes=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert len(pe) == 1
            assert VideoTemplates.private_confirmed(6, 21) == pe[0].data.get("text")
            mocks.video_service.record_late.assert_not_called()

    async def test_delay_30_not_late(self, mocks: MockHolder):
        """Boundary: 30 is NOT late (strict >)."""
        _setup_confirm(mocks, log=_log(delay_minutes=30))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert VideoTemplates.private_confirmed(6, 21) == pe[0].data.get("text")
            mocks.video_service.record_late.assert_not_called()

    async def test_delay_31_is_late(self, mocks: MockHolder):
        """Boundary: 31 IS late → approved_late in private."""
        _setup_confirm(
            mocks, log=_log(delay_minutes=31),
            late_result=(1, ["2025-01-15T10:31:00+05:00"]),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert len(pe) == 1
            assert VideoTemplates.approved_late(6, 21, 1, 3) == pe[0].data.get("text")
            mocks.video_service.record_late.assert_called_once()


class TestOnConfirmLateStrike:
    """Late confirm without removal (late_count < max_strikes)."""

    async def test_late_records_strike(self, mocks: MockHolder):
        _setup_confirm(
            mocks, log=_log(delay_minutes=60),
            late_result=(1, ["2025-01-15T10:31:00+05:00"]),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            mocks.video_service.record_late.assert_called_once()
            pe = _private_edits(bot)
            assert VideoTemplates.approved_late(6, 21, 1, 3) == pe[0].data.get("text")

    async def test_late_warning_in_topic(self, mocks: MockHolder):
        _setup_confirm(
            mocks, log=_log(delay_minutes=60),
            late_result=(2, ["d1", "d2"]),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            sends = _group_sends(bot, topic_id=TOPIC_ID)
            assert len(sends) == 1
            assert VideoTemplates.topic_late_warning(2, 3) == sends[0].data.get("text")

    async def test_late_record_fails_still_confirms(self, mocks: MockHolder):
        """record_late raises → is_late reset to False, shows normal confirmed."""
        _setup_confirm(mocks, log=_log(delay_minutes=60))
        mocks.video_service.record_late.side_effect = RuntimeError("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            # Strike not recorded → show normal confirmed, not late warning
            pe = _private_edits(bot)
            assert VideoTemplates.private_confirmed(6, 21) == pe[0].data.get("text")
            mocks.video_service.undo_day_and_refuse.assert_not_called()

    async def test_first_day_late_overrides_icon(self, mocks: MockHolder):
        """day=1 + is_late → late warning sent, NOT icon change to ACTIVE."""
        _setup_confirm(
            mocks, log=_log(day=1, delay_minutes=60),
            late_result=(1, ["d1"]),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            # Late warning in topic
            sends = _group_sends(bot, topic_id=TOPIC_ID)
            assert len(sends) == 1
            assert VideoTemplates.topic_late_warning(1, 3) == sends[0].data.get("text")
            # No icon change (late branch takes priority over day==1)
            assert len(_forum_edits(bot)) == 0


class TestOnConfirmLateRemoval:
    """Late removal: late_count >= max_strikes."""

    def _setup(self, mocks: MockHolder, **kw: Any) -> None:
        _setup_confirm(
            mocks,
            log=kw.get("log", _log(delay_minutes=60)),
            course=kw.get("course", _course(late_count=2)),
            user=kw.get("user", _user()),
            manager=kw.get("manager", _manager()),
            max_strikes=kw.get("max_strikes", 3),
            late_result=kw.get("late_result", (3, LATE_DATES)),
        )

    async def test_removal_triggers(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            mocks.video_service.undo_day_and_refuse.assert_called_once()

    async def test_removal_undo_original_day(self, mocks: MockHolder):
        """undo_day_and_refuse uses course.current_day BEFORE increment."""
        self._setup(mocks, course=_course(current_day=5, late_count=2))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            mocks.video_service.undo_day_and_refuse.assert_called_once_with(
                COURSE_ID, 5, appeal_deadline=ANY,
            )

    async def test_removal_topic_message(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            cb = _callback_edits(bot)
            assert len(cb) >= 1
            assert "Снята с программы" in cb[0].data.get("text", "")

    async def test_removal_private_with_appeal(self, mocks: MockHolder):
        self._setup(mocks, course=_course(late_count=2, appeal_count=0))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert len(pe) == 1
            assert "опоздала слишком много" in pe[0].data.get("text", "")
            assert _has_appeal_button(pe[0].data)

    async def test_removal_no_appeal_at_max(self, mocks: MockHolder):
        """appeal_count >= MAX_APPEALS → no appeal button."""
        self._setup(mocks, course=_course(late_count=2, appeal_count=2))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert len(pe) == 1
            assert not _has_appeal_button(pe[0].data)

    async def test_removal_icon_refused(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            fe = _forum_edits(bot)
            assert len(fe) == 1
            assert fe[0].data.get("icon_custom_emoji_id") == str(TOPIC_ICON_REFUSED)

    async def test_removal_general_topic(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            sends = _group_sends(bot, topic_id=KOK_GENERAL_TOPIC_ID)
            assert len(sends) == 1
            text = sends[0].data.get("text", "")
            assert "снята" in text
            assert "Test Manager отклонил видео" in text
            assert "Test Girl" in text

    async def test_removal_no_general_topic_id(self, mocks: MockHolder):
        """kok_general_topic_id=None → send without message_thread_id."""
        mocks.settings.kok_general_topic_id = None
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            sends = _group_sends(bot)
            general = [s for s in sends if "снята" in s.data.get("text", "")]
            assert len(general) == 1
            assert "message_thread_id" not in general[0].data

    async def test_removal_manager_not_found(self, mocks: MockHolder):
        """manager_repo returns None → fallback 'менеджер'."""
        self._setup(mocks)
        mocks.manager_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert "менеджер" in pe[0].data.get("text", "")

    async def test_removal_icon_fails_silent(self, mocks: MockHolder):
        """editForumTopic fails → handler continues to general topic."""
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            _fail(bot, "editForumTopic")
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            sends = _group_sends(bot)
            assert any("снята" in s.data.get("text", "") for s in sends)
            assert len(_answers(bot)) >= 1

    async def test_removal_general_send_fails(self, mocks: MockHolder):
        """sendMessage to general fails → handler still answers callback."""
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            _fail(bot, "sendMessage")
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1


class TestOnConfirmCompletion:
    """Completion: day >= total_days, not removal."""

    def _setup(self, mocks: MockHolder, **kw: Any) -> None:
        _setup_confirm(
            mocks,
            log=kw.get("log", _log(day=21)),
            course=kw.get("course", _course(total_days=21)),
            user=kw.get("user", _user()),
        )

    async def test_completion_on_last_day(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            mocks.video_service.complete_course.assert_called_once_with(COURSE_ID)

    async def test_completion_topic_message(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            cb = _callback_edits(bot)
            assert VideoTemplates.topic_completed(21, 21) == cb[0].data.get("text")

    async def test_completion_private_message(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert len(pe) == 1
            assert VideoTemplates.private_completed(21) == pe[0].data.get("text")

    async def test_completion_icon(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            fe = _forum_edits(bot)
            assert len(fe) == 1
            assert fe[0].data.get("icon_custom_emoji_id") == str(TOPIC_ICON_COMPLETED)

    async def test_completion_topic_closed(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_forum_closes(bot)) == 1

    async def test_completion_fails_fallback(self, mocks: MockHolder):
        """complete_course raises → is_completed=False → topic_confirmed."""
        self._setup(mocks)
        mocks.video_service.complete_course.side_effect = RuntimeError("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            cb = _callback_edits(bot)
            assert VideoTemplates.topic_confirmed(21, 21) == cb[0].data.get("text")
            # No completion icon/close
            assert len(_forum_closes(bot)) == 0

    async def test_completion_icon_fails_silent(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            _fail(bot, "editForumTopic")
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            # close_forum_topic still called
            assert len(_forum_closes(bot)) == 1
            assert len(_answers(bot)) >= 1

    async def test_completion_close_fails_silent(self, mocks: MockHolder):
        self._setup(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            _fail(bot, "closeForumTopic")
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            # Icon still changed
            fe = _forum_edits(bot)
            assert len(fe) == 1
            assert len(_answers(bot)) >= 1


class TestOnConfirmEdgeCases:
    """Private/topic skip conditions + remaining failure branches."""

    async def test_no_completion_on_removal(self, mocks: MockHolder):
        """day=total but removal → is_completed=False."""
        _setup_confirm(
            mocks,
            log=_log(day=21, delay_minutes=60),
            course=_course(total_days=21, late_count=2),
            late_result=(3, LATE_DATES),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            mocks.video_service.complete_course.assert_not_called()
            mocks.video_service.undo_day_and_refuse.assert_called_once()

    async def test_user_none_skips_private_and_topic(self, mocks: MockHolder):
        _setup_confirm(mocks, user=None)
        mocks.user_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_private_edits(bot)) == 0
            assert len(_forum_edits(bot)) == 0

    async def test_no_telegram_id_skips_private(self, mocks: MockHolder):
        _setup_confirm(mocks, user=_user(telegram_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_private_edits(bot)) == 0

    async def test_no_private_msg_id_skips_private(self, mocks: MockHolder):
        _setup_confirm(mocks, log=_log(private_message_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_private_edits(bot)) == 0

    async def test_no_topic_id_skips_topic_actions(self, mocks: MockHolder):
        _setup_confirm(mocks, user=_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_forum_edits(bot)) == 0
            assert len(_group_sends(bot)) == 0

    async def test_late_warning_send_fails(self, mocks: MockHolder):
        """sendMessage for late warning fails → handler continues."""
        _setup_confirm(
            mocks, log=_log(delay_minutes=60),
            late_result=(1, ["d1"]),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            _fail(bot, "sendMessage")
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1

    async def test_first_day_icon_fails(self, mocks: MockHolder):
        """editForumTopic for day=1 icon fails → handler continues."""
        _setup_confirm(mocks, log=_log(day=1))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            _fail(bot, "editForumTopic")
            await bot.click_button(_confirm(), message_id=CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1


# ═════════════════════════════════════════════════════════════════════════
# on_reject (lines 218-279)
# ═════════════════════════════════════════════════════════════════════════


class TestOnReject:
    """Manager rejects video → refuse course."""

    async def test_log_not_found(self, mocks: MockHolder):
        mocks.intake_log_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1
            mocks.video_service.reject_intake.assert_not_called()

    async def test_log_wrong_status(self, mocks: MockHolder):
        mocks.intake_log_repo.get_by_id.return_value = _log(status="rejected")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1

    async def test_course_not_found(self, mocks: MockHolder):
        mocks.intake_log_repo.get_by_id.return_value = _log()
        mocks.course_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            assert "курс не найден" in _answers(bot)[0].data.get("text", "")

    async def test_reject_calls_service(self, mocks: MockHolder):
        _setup_reject(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            mocks.video_service.reject_intake.assert_called_once_with(LOG_ID, COURSE_ID)

    async def test_reject_topic_message(self, mocks: MockHolder):
        _setup_reject(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            cb = _callback_edits(bot)
            assert len(cb) >= 1
            assert VideoTemplates.topic_rejected() == cb[0].data.get("text")

    async def test_reject_private_no_appeal(self, mocks: MockHolder):
        """Manager reject = manager decision → no appeal button."""
        _setup_reject(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert len(pe) == 1
            assert "Менеджер отклонил видео" in pe[0].data.get("text", "")
            assert not _has_appeal_button(pe[0].data)

    async def test_reject_icon_refused(self, mocks: MockHolder):
        _setup_reject(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            fe = _forum_edits(bot)
            assert len(fe) == 1
            assert fe[0].data.get("icon_custom_emoji_id") == str(TOPIC_ICON_REFUSED)

    async def test_callback_answered(self, mocks: MockHolder):
        _setup_reject(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1

    async def test_manager_not_found(self, mocks: MockHolder):
        _setup_reject(mocks)
        mocks.manager_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            pe = _private_edits(bot)
            assert "менеджер" in pe[0].data.get("text", "")

    async def test_user_none_skips_all(self, mocks: MockHolder):
        _setup_reject(mocks)
        mocks.user_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            assert len(_forum_edits(bot)) == 0
            assert len(_private_edits(bot)) == 0

    async def test_no_topic_id_skips_icon(self, mocks: MockHolder):
        _setup_reject(mocks, user=_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            assert len(_forum_edits(bot)) == 0

    async def test_icon_fails_silent(self, mocks: MockHolder):
        _setup_reject(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            _fail(bot, "editForumTopic")
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1

    async def test_no_telegram_id_skips_private(self, mocks: MockHolder):
        _setup_reject(mocks, user=_user(telegram_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            assert len(_private_edits(bot)) == 0

    async def test_no_private_msg_id_skips_private(self, mocks: MockHolder):
        _setup_reject(mocks, log=_log(private_message_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reject(), message_id=CALLBACK_MSG_ID)
            assert len(_private_edits(bot)) == 0


# ═════════════════════════════════════════════════════════════════════════
# on_reshoot (lines 282-339)
# ═════════════════════════════════════════════════════════════════════════


class TestOnReshoot:
    """Manager requests reshoot → set deadline, notify girl."""

    async def test_log_not_found(self, mocks: MockHolder):
        mocks.intake_log_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1
            mocks.video_service.request_reshoot.assert_not_called()

    async def test_log_wrong_status(self, mocks: MockHolder):
        mocks.intake_log_repo.get_by_id.return_value = _log(status="reshoot")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1

    async def test_course_not_found(self, mocks: MockHolder):
        mocks.intake_log_repo.get_by_id.return_value = _log()
        mocks.course_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            assert "курс не найден" in _answers(bot)[0].data.get("text", "")

    async def test_reshoot_calls_service(self, mocks: MockHolder):
        _setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            mocks.video_service.request_reshoot.assert_called_once_with(LOG_ID, _course())

    async def test_reshoot_topic_message(self, mocks: MockHolder):
        _setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            cb = _callback_edits(bot)
            assert len(cb) >= 1
            text = cb[0].data.get("text", "")
            assert "переснять видео" in text
            assert DEADLINE_STR in text
            assert "осталось" in text

    async def test_reshoot_private_message(self, mocks: MockHolder):
        _setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            ps = _private_sends(bot)
            assert len(ps) == 1
            text = ps[0].data.get("text", "")
            assert "переснять видео" in text
            assert DEADLINE_STR in text
            assert "осталось" in text

    async def test_reshoot_icon(self, mocks: MockHolder):
        _setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            fe = _forum_edits(bot)
            assert len(fe) == 1
            assert fe[0].data.get("icon_custom_emoji_id") == str(TOPIC_ICON_RESHOOT)

    async def test_callback_answered(self, mocks: MockHolder):
        _setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1

    async def test_user_none_skips_all(self, mocks: MockHolder):
        _setup_reshoot(mocks)
        mocks.user_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            assert len(_private_sends(bot)) == 0
            assert len(_forum_edits(bot)) == 0

    async def test_no_topic_id_skips_icon(self, mocks: MockHolder):
        _setup_reshoot(mocks, user=_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            assert len(_forum_edits(bot)) == 0

    async def test_icon_fails_silent(self, mocks: MockHolder):
        _setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            _fail(bot, "editForumTopic")
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1

    async def test_no_telegram_id_skips_private(self, mocks: MockHolder):
        _setup_reshoot(mocks, user=_user(telegram_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            _seed(bot)
            await bot.click_button(_reshoot(), message_id=CALLBACK_MSG_ID)
            assert len(_private_sends(bot)) == 0