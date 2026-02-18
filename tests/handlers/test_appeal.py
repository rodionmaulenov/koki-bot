"""Tests for handlers/appeal.py — appeal flow + scenario tests."""
from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Update
from aiogram.types import User as TgUser

from callbacks.appeal import AppealAction, AppealCallback
from handlers.appeal import (
    TOPIC_ICON_ACTIVE,
    TOPIC_ICON_APPEAL,
    TOPIC_ICON_REFUSED,
)
from models.course import Course
from models.enums import CourseStatus
from models.manager import Manager
from models.user import User as KokUser
from states.appeal import AppealStates
from templates import AppealTemplates
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
COURSE_ID = 10
CALLBACK_MSG_ID = 1
REG_MSG_ID = 200

_S_GROUP = str(KOK_GROUP_ID)
_S_GENERAL = str(KOK_GENERAL_TOPIC_ID)

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
        id=COURSE_ID, user_id=1, status=CourseStatus.REFUSED,
        intake_time=time(10, 0), current_day=5, total_days=21,
        late_count=0, appeal_count=0, late_dates=[],
        removal_reason="no_video",
        registration_message_id=REG_MSG_ID,
        created_at=datetime(2025, 1, 1, tzinfo=TASHKENT_TZ),
    )
    d.update(ov)
    return Course(**d)


def _manager(**ov: Any) -> Manager:
    d: dict[str, Any] = dict(
        id=1, telegram_id=MANAGER_TG_ID, name="Test Manager",
        is_active=True, created_at=datetime(2025, 1, 1, tzinfo=TASHKENT_TZ),
    )
    d.update(ov)
    return Manager(**d)


# ── Callback data ─────────────────────────────────────────────────────────


def _start_cb(course_id: int = COURSE_ID) -> str:
    return AppealCallback(action=AppealAction.START, course_id=course_id).pack()


def _accept_cb(course_id: int = COURSE_ID) -> str:
    return AppealCallback(action=AppealAction.ACCEPT, course_id=course_id).pack()


def _decline_cb(course_id: int = COURSE_ID) -> str:
    return AppealCallback(action=AppealAction.DECLINE, course_id=course_id).pack()


# ── Mock setup ────────────────────────────────────────────────────────────


def _setup_start(m: MockHolder, **kw: Any) -> None:
    m.course_repo.get_by_id.return_value = kw.get("course", _course())
    m.course_repo.start_appeal.return_value = kw.get("started", True)


def _setup_text(m: MockHolder, **kw: Any) -> None:
    m.course_repo.save_appeal_data.return_value = None
    m.course_repo.get_by_id.return_value = kw.get(
        "course", _course(status=CourseStatus.APPEAL),
    )
    m.user_repo.get_by_id.return_value = kw.get("user", _user())
    m.manager_repo.get_by_id.return_value = kw.get("manager", _manager())
    m.video_service.calculate_deadline.return_value = kw.get("deadline", DEADLINE)
    if kw.get("save_error"):
        m.course_repo.save_appeal_data.side_effect = Exception("DB error")


def _setup_accept(m: MockHolder, **kw: Any) -> None:
    m.course_repo.get_by_id.return_value = kw.get(
        "course", _course(status=CourseStatus.APPEAL),
    )
    m.course_repo.accept_appeal.return_value = kw.get("accepted", True)
    m.user_repo.get_by_id.return_value = kw.get("user", _user())


def _setup_decline(m: MockHolder, **kw: Any) -> None:
    m.course_repo.get_by_id.return_value = kw.get(
        "course", _course(status=CourseStatus.APPEAL),
    )
    m.course_repo.decline_appeal.return_value = kw.get("declined", True)
    m.user_repo.get_by_id.return_value = kw.get("user", _user())
    m.manager_repo.get_by_id.return_value = kw.get("manager", _manager())


# ── Tracker helpers ───────────────────────────────────────────────────────


def _sends(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("sendMessage")


def _private_sends(bot: MockTelegramBot) -> list[TrackedRequest]:
    return [r for r in _sends(bot) if str(r.data.get("chat_id")) == str(USER_ID)]


def _manager_sends(bot: MockTelegramBot) -> list[TrackedRequest]:
    return [r for r in _sends(bot) if str(r.data.get("chat_id")) == str(MANAGER_TG_ID)]


def _group_sends(
    bot: MockTelegramBot, topic_id: int | None = None,
) -> list[TrackedRequest]:
    out = []
    for r in _sends(bot):
        if str(r.data.get("chat_id")) == _S_GROUP:
            if topic_id is None or str(r.data.get("message_thread_id")) == str(topic_id):
                out.append(r)
    return out


def _edits(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("editMessageText")


def _edit_markups(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("editMessageReplyMarkup")


def _forum_edits(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("editForumTopic")


def _forum_closes(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("closeForumTopic")


def _forum_reopens(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("reopenForumTopic")


def _videos_sent(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("sendVideo")


def _answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("answerCallbackQuery")


def _is_alert(r: TrackedRequest) -> bool:
    return str(r.data.get("show_alert", "")).lower() in ("true", "1")


def _alert_answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return [r for r in _answers(bot) if _is_alert(r)]


def _has_review_buttons(data: dict[str, Any]) -> bool:
    markup = data.get("reply_markup")
    if not markup:
        return False
    if isinstance(markup, str):
        markup = json.loads(markup)
    for row in markup.get("inline_keyboard", []):
        for btn in row:
            if "Принять" in btn.get("text", "") or "Отклонить" in btn.get("text", ""):
                return True
    return False


def _card_button_texts(bot: MockTelegramBot) -> list[str]:
    """Get button texts from editMessageReplyMarkup to GROUP."""
    for r in _edit_markups(bot):
        if str(r.data.get("chat_id")) == _S_GROUP:
            markup = r.data.get("reply_markup")
            if isinstance(markup, str):
                markup = json.loads(markup)
            if not markup:
                continue
            texts = []
            for row in markup.get("inline_keyboard", []):
                for btn in row:
                    texts.append(btn.get("text", ""))
            return texts
    return []


# ── Seed / FSM / Fail helpers ────────────────────────────────────────────


def _seed(bot: MockTelegramBot) -> None:
    """Pre-add callback message so edits work on mock server."""
    bot.chat_state.add_message(
        chat_id=bot.chat_id, from_user_id=BOT_ID, is_bot=True,
        text="review message", message_id=CALLBACK_MSG_ID,
    )


def _seed_reg_card(bot: MockTelegramBot) -> None:
    """Pre-add registration card in group for editMessageReplyMarkup."""
    bot.chat_state.add_message(
        chat_id=KOK_GROUP_ID, from_user_id=BOT_ID, is_bot=True,
        text="reg card", message_id=REG_MSG_ID,
        message_thread_id=TOPIC_ID,
    )


async def _set_fsm(dp, state_name, data: dict | None = None) -> None:
    key = StorageKey(bot_id=BOT_ID, chat_id=USER_ID, user_id=USER_ID)
    await dp.storage.set_state(key, state_name)
    if data:
        await dp.storage.set_data(key, data)


async def _get_fsm_state(dp) -> str | None:
    key = StorageKey(bot_id=BOT_ID, chat_id=USER_ID, user_id=USER_ID)
    return await dp.storage.get_state(key)


async def _get_fsm_data(dp) -> dict:
    key = StorageKey(bot_id=BOT_ID, chat_id=USER_ID, user_id=USER_ID)
    return await dp.storage.get_data(key)


def _fail(bot: MockTelegramBot, method_name: str, error_code: int = 500) -> None:
    orig = bot._server._route_method

    def patched(method, data):
        if method == method_name:
            return {"ok": False, "error_code": error_code, "description": "Mock error"}
        return orig(method, data)

    bot._server._route_method = patched


def _fail_for_chat(
    bot: MockTelegramBot, method_name: str, chat_id: int, error_code: int = 500,
) -> None:
    orig = bot._server._route_method

    def patched(method, data):
        if method == method_name and str(data.get("chat_id")) == str(chat_id):
            return {"ok": False, "error_code": error_code, "description": "Mock error"}
        return orig(method, data)

    bot._server._route_method = patched


def _fail_match(
    bot: MockTelegramBot, method_name: str, error_code: int = 500, **match_data: Any,
) -> None:
    orig = bot._server._route_method

    def patched(method, data):
        if method == method_name and all(
            str(data.get(k)) == str(v) for k, v in match_data.items()
        ):
            return {"ok": False, "error_code": error_code, "description": "Mock error"}
        return orig(method, data)

    bot._server._route_method = patched


def _make_callback_update(callback_data: str) -> Update:
    """Create callback Update WITHOUT message (for callback_message_none tests)."""
    return Update(
        update_id=1,
        callback_query=CallbackQuery(
            id="cb_test",
            from_user=TgUser(id=USER_ID, is_bot=False, first_name="Test"),
            chat_instance=str(USER_ID),
            data=callback_data,
        ),
    )


# ══════════════════════════════════════════════════════════════════════════
# on_start_appeal — Girl clicks "Апелляция" button
# ══════════════════════════════════════════════════════════════════════════


class TestOnStartAppeal:

    async def test_course_not_found(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1

    async def test_course_not_refused(self, mocks: MockHolder) -> None:
        _setup_start(mocks, course=_course(status=CourseStatus.ACTIVE))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1

    async def test_max_appeals_reached(self, mocks: MockHolder) -> None:
        _setup_start(mocks, course=_course(appeal_count=AppealTemplates.MAX_APPEALS))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1

    async def test_race_condition(self, mocks: MockHolder) -> None:
        _setup_start(mocks, started=False)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert AppealTemplates.appeal_race_condition() in alerts[0].data.get("text", "")

    async def test_happy_path(self, mocks: MockHolder) -> None:
        _setup_start(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)

            # FSM state → video
            assert await _get_fsm_state(dp) == AppealStates.video.state
            assert (await _get_fsm_data(dp))["course_id"] == COURSE_ID

            # Girl received ask_video
            private = _private_sends(bot)
            assert len(private) == 1
            assert AppealTemplates.ask_video() in private[0].data.get("text", "")

            # Reply markup removed
            assert len(_edit_markups(bot)) >= 1

            # Callback answered (not alert)
            assert len(_answers(bot)) >= 1
            assert len(_alert_answers(bot)) == 0

    async def test_edit_reply_markup_fails_silently(self, mocks: MockHolder) -> None:
        _setup_start(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "editMessageReplyMarkup", 400)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)

            # Despite edit failure, FSM set and message sent
            assert await _get_fsm_state(dp) == AppealStates.video.state
            assert len(_private_sends(bot)) == 1

    async def test_girl_blocked_bot(self, mocks: MockHolder) -> None:
        _setup_start(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_for_chat(bot, "sendMessage", USER_ID, 403)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)

            # FSM cleared
            assert await _get_fsm_state(dp) is None

            # Callback still answered
            assert len(_answers(bot)) >= 1

    async def test_callback_message_none(self, mocks: MockHolder) -> None:
        _setup_start(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await dp.feed_update(bot.bot, _make_callback_update(_start_cb()))

            # No edit (no message to edit)
            assert len(_edit_markups(bot)) == 0

            # FSM still set
            assert await _get_fsm_state(dp) == AppealStates.video.state
            assert len(_private_sends(bot)) == 1

    async def test_blocked_by_manager_reject(self, mocks: MockHolder) -> None:
        """removal_reason=manager_reject → appeal denied."""
        _setup_start(mocks, course=_course(removal_reason="manager_reject"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            ans = _answers(bot)
            assert any(a.data.get("show_alert") == "true" for a in ans)
            mocks.course_repo.start_appeal.assert_not_called()

    async def test_blocked_by_review_deadline(self, mocks: MockHolder) -> None:
        """removal_reason=review_deadline → appeal denied."""
        _setup_start(mocks, course=_course(removal_reason="review_deadline"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            ans = _answers(bot)
            assert any(a.data.get("show_alert") == "true" for a in ans)
            mocks.course_repo.start_appeal.assert_not_called()

    async def test_blocked_by_reshoot_expired(self, mocks: MockHolder) -> None:
        """removal_reason=reshoot_expired → appeal denied."""
        _setup_start(mocks, course=_course(removal_reason="reshoot_expired"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            ans = _answers(bot)
            assert any(a.data.get("show_alert") == "true" for a in ans)
            mocks.course_repo.start_appeal.assert_not_called()

    async def test_allowed_for_no_video(self, mocks: MockHolder) -> None:
        """removal_reason=no_video → appeal allowed."""
        _setup_start(mocks, course=_course(removal_reason="no_video"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            mocks.course_repo.start_appeal.assert_called_once()
            assert await _get_fsm_state(dp) == AppealStates.video.state

    async def test_allowed_for_max_strikes(self, mocks: MockHolder) -> None:
        """removal_reason=max_strikes → appeal allowed."""
        _setup_start(mocks, course=_course(removal_reason="max_strikes"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            mocks.course_repo.start_appeal.assert_called_once()
            assert await _get_fsm_state(dp) == AppealStates.video.state

    async def test_blocked_legacy_null_removal_reason(self, mocks: MockHolder) -> None:
        """removal_reason=None (legacy course before migration) → appeal denied."""
        _setup_start(mocks, course=_course(removal_reason=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1
            mocks.course_repo.start_appeal.assert_not_called()
            assert await _get_fsm_state(dp) is None

    async def test_blocked_by_appeal_declined(self, mocks: MockHolder) -> None:
        """removal_reason=appeal_declined → appeal denied (can't re-appeal declined)."""
        _setup_start(mocks, course=_course(removal_reason="appeal_declined"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1
            mocks.course_repo.start_appeal.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# Appeal FSM Step 1 — Video
# ══════════════════════════════════════════════════════════════════════════


class TestAppealVideoStep:

    async def test_video_note_accepted(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.video, {"course_id": COURSE_ID})
            await bot.send_video_note(file_id="appeal_vn")

            assert await _get_fsm_state(dp) == AppealStates.text.state
            assert (await _get_fsm_data(dp))["appeal_video"] == "appeal_vn"
            msgs = _private_sends(bot)
            assert any(AppealTemplates.ask_text() in m.data.get("text", "") for m in msgs)

    async def test_video_accepted(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.video, {"course_id": COURSE_ID})
            await bot.send_video(file_id="appeal_vid")

            assert await _get_fsm_state(dp) == AppealStates.text.state
            assert (await _get_fsm_data(dp))["appeal_video"] == "appeal_vid"

    async def test_document_video_mp4_accepted(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.video, {"course_id": COURSE_ID})
            await bot.send_document(
                file_id="appeal_doc", mime_type="video/mp4",
            )

            assert await _get_fsm_state(dp) == AppealStates.text.state
            assert (await _get_fsm_data(dp))["appeal_video"] == "appeal_doc"

    async def test_document_non_video_rejected(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.video, {"course_id": COURSE_ID})
            await bot.send_document(mime_type="application/pdf")

            # Still in video state
            assert await _get_fsm_state(dp) == AppealStates.video.state
            msgs = _private_sends(bot)
            assert any(AppealTemplates.video_only() in m.data.get("text", "") for m in msgs)

    async def test_document_empty_mime_rejected(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.video, {"course_id": COURSE_ID})
            await bot.send_document(mime_type="")

            assert await _get_fsm_state(dp) == AppealStates.video.state

    async def test_photo_rejected(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.video, {"course_id": COURSE_ID})
            await bot.send_photo()

            assert await _get_fsm_state(dp) == AppealStates.video.state
            msgs = _private_sends(bot)
            assert any(AppealTemplates.video_only() in m.data.get("text", "") for m in msgs)

    async def test_text_rejected(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.video, {"course_id": COURSE_ID})
            await bot.send_message("hello")

            assert await _get_fsm_state(dp) == AppealStates.video.state
            msgs = _private_sends(bot)
            assert any(AppealTemplates.video_only() in m.data.get("text", "") for m in msgs)

    async def test_video_file_id_saved(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.video, {"course_id": COURSE_ID})
            await bot.send_video_note(file_id="specific_file_123")

            data = await _get_fsm_data(dp)
            assert data["appeal_video"] == "specific_file_123"
            assert data["course_id"] == COURSE_ID

    async def test_document_mime_video_quicktime(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.video, {"course_id": COURSE_ID})
            await bot.send_document(
                file_id="qt_video", mime_type="video/quicktime",
            )

            assert await _get_fsm_state(dp) == AppealStates.text.state
            assert (await _get_fsm_data(dp))["appeal_video"] == "qt_video"


# ══════════════════════════════════════════════════════════════════════════
# Appeal FSM Step 2 — Text (on_appeal_text)
# ══════════════════════════════════════════════════════════════════════════


class TestAppealTextStep:

    _FSM_DATA: dict[str, Any] = {"course_id": COURSE_ID, "appeal_video": "vid_file"}

    async def test_missing_course_id(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, {"appeal_video": "vid"})
            await bot.send_message("My appeal")

            assert await _get_fsm_state(dp) is None
            msgs = _private_sends(bot)
            assert any(
                AppealTemplates.appeal_race_condition() in m.data.get("text", "")
                for m in msgs
            )

    async def test_missing_appeal_video(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, {"course_id": COURSE_ID})
            await bot.send_message("My appeal")

            assert await _get_fsm_state(dp) is None

    async def test_empty_text(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("   ")

            # Still in text state (not cleared)
            assert await _get_fsm_state(dp) == AppealStates.text.state
            msgs = _private_sends(bot)
            assert any(AppealTemplates.text_only() in m.data.get("text", "") for m in msgs)

    async def test_save_appeal_data_fails(self, mocks: MockHolder) -> None:
        _setup_text(mocks, save_error=True)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("My appeal text")

            assert await _get_fsm_state(dp) is None
            msgs = _private_sends(bot)
            assert any(
                AppealTemplates.appeal_race_condition() in m.data.get("text", "")
                for m in msgs
            )

    async def test_happy_path_full(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("My appeal reason")

            # FSM cleared
            assert await _get_fsm_state(dp) is None

            # save_appeal_data called correctly
            mocks.course_repo.save_appeal_data.assert_called_once_with(
                COURSE_ID, "vid_file", "My appeal reason",
            )

            # Girl notified
            private = _private_sends(bot)
            assert any(
                AppealTemplates.appeal_submitted() in m.data.get("text", "")
                for m in private
            )

            # Topic reopened
            assert len(_forum_reopens(bot)) == 1

            # Topic icon → ❓
            fe = _forum_edits(bot)
            assert any(
                str(TOPIC_ICON_APPEAL) in str(r.data.get("icon_custom_emoji_id", ""))
                for r in fe
            )

            # Video sent to topic
            vids = _videos_sent(bot)
            assert len(vids) == 1
            assert str(vids[0].data.get("chat_id")) == _S_GROUP
            assert str(vids[0].data.get("message_thread_id")) == str(TOPIC_ID)
            assert vids[0].data.get("video") == "vid_file"

            # Text + review buttons to topic
            topic_msgs = _group_sends(bot, TOPIC_ID)
            assert len(topic_msgs) >= 1
            assert "My appeal reason" in topic_msgs[0].data.get("text", "")
            assert _has_review_buttons(topic_msgs[0].data)

            # Manager DM
            mgr = _manager_sends(bot)
            assert len(mgr) == 1
            assert "Test Girl" in mgr[0].data.get("text", "")
            assert DEADLINE_STR in mgr[0].data.get("text", "")

            # General topic
            gen = _group_sends(bot, KOK_GENERAL_TOPIC_ID)
            assert len(gen) == 1
            assert "Test Manager" in gen[0].data.get("text", "")
            assert "Test Girl" in gen[0].data.get("text", "")

    async def test_course_not_found_after_save(self, mocks: MockHolder) -> None:
        _setup_text(mocks, course=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            # Girl still notified
            assert any(
                AppealTemplates.appeal_submitted() in m.data.get("text", "")
                for m in _private_sends(bot)
            )
            # But no topic operations
            assert len(_forum_reopens(bot)) == 0
            assert len(_videos_sent(bot)) == 0

    async def test_user_not_found(self, mocks: MockHolder) -> None:
        _setup_text(mocks, user=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            assert any(
                AppealTemplates.appeal_submitted() in m.data.get("text", "")
                for m in _private_sends(bot)
            )
            assert len(_forum_reopens(bot)) == 0

    async def test_user_no_topic_id(self, mocks: MockHolder) -> None:
        _setup_text(mocks, user=_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            assert len(_forum_reopens(bot)) == 0
            assert len(_videos_sent(bot)) == 0

    async def test_reopen_topic_bad_request_ignored(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _fail(bot, "reopenForumTopic", 400)
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            # Despite reopen failure, general topic message sent
            assert len(_group_sends(bot, KOK_GENERAL_TOPIC_ID)) == 1

    async def test_reopen_topic_other_error_ignored(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _fail(bot, "reopenForumTopic", 500)
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            assert len(_group_sends(bot, KOK_GENERAL_TOPIC_ID)) == 1

    async def test_edit_topic_icon_fails(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _fail(bot, "editForumTopic", 500)
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            assert len(_manager_sends(bot)) == 1

    async def test_send_video_to_topic_fails(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _fail(bot, "sendVideo", 500)
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            # Text+buttons still sent despite video failure
            assert len(_group_sends(bot, TOPIC_ID)) >= 1

    async def test_send_text_to_topic_fails(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _fail_match(
                bot, "sendMessage", 500,
                chat_id=KOK_GROUP_ID, message_thread_id=TOPIC_ID,
            )
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            # Manager DM still sent despite topic text failure
            assert len(_manager_sends(bot)) == 1

    async def test_manager_not_found(self, mocks: MockHolder) -> None:
        _setup_text(mocks, manager=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            # No DM and no general topic message
            assert len(_manager_sends(bot)) == 0
            assert len(_group_sends(bot, KOK_GENERAL_TOPIC_ID)) == 0

    async def test_manager_blocked_bot(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _fail_for_chat(bot, "sendMessage", MANAGER_TG_ID, 403)
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            # General topic still sent despite manager DM failure
            assert len(_group_sends(bot, KOK_GENERAL_TOPIC_ID)) == 1

    async def test_manager_dm_other_error(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _fail_for_chat(bot, "sendMessage", MANAGER_TG_ID, 500)
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            assert len(_group_sends(bot, KOK_GENERAL_TOPIC_ID)) == 1

    async def test_general_topic_send_fails(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _fail_match(
                bot, "sendMessage", 500,
                chat_id=KOK_GROUP_ID, message_thread_id=KOK_GENERAL_TOPIC_ID,
            )
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            # Handler completed without error (silent failure)
            assert await _get_fsm_state(dp) is None

    async def test_general_topic_no_thread_id(self, mocks: MockHolder) -> None:
        _setup_text(mocks)
        mocks.settings.kok_general_topic_id = 0
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, self._FSM_DATA.copy())
            await bot.send_message("Appeal text")

            # General message sent to GROUP WITHOUT message_thread_id
            group_no_thread = [
                r for r in _sends(bot)
                if str(r.data.get("chat_id")) == _S_GROUP
                and not r.data.get("message_thread_id")
            ]
            # Exclude topic messages (they have thread_id)
            assert len(group_no_thread) >= 1


# ══════════════════════════════════════════════════════════════════════════
# Appeal FSM Step 2 — Invalid content
# ══════════════════════════════════════════════════════════════════════════


class TestAppealTextInvalid:

    async def test_photo_rejected(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, {"course_id": COURSE_ID, "appeal_video": "v"})
            await bot.send_photo()

            assert await _get_fsm_state(dp) == AppealStates.text.state
            msgs = _private_sends(bot)
            assert any(AppealTemplates.text_only() in m.data.get("text", "") for m in msgs)

    async def test_video_rejected(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await _set_fsm(dp, AppealStates.text, {"course_id": COURSE_ID, "appeal_video": "v"})
            await bot.send_video()

            assert await _get_fsm_state(dp) == AppealStates.text.state
            msgs = _private_sends(bot)
            assert any(AppealTemplates.text_only() in m.data.get("text", "") for m in msgs)


# ══════════════════════════════════════════════════════════════════════════
# on_appeal_accept — Manager accepts appeal
# ══════════════════════════════════════════════════════════════════════════


class TestOnAppealAccept:

    # ── Guards ────────────────────────────────────────────────────────────

    async def test_course_not_found(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1

    async def test_course_not_appeal_status(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, course=_course(status=CourseStatus.ACTIVE))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1

    async def test_race_condition(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, accepted=False)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert AppealTemplates.appeal_already_handled() in alerts[0].data.get("text", "")

    # ── Happy path ────────────────────────────────────────────────────────

    async def test_happy_path_first_appeal(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, course=_course(status=CourseStatus.APPEAL, appeal_count=0))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _seed_reg_card(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            # accept_appeal called with count=1
            mocks.course_repo.accept_appeal.assert_called_once_with(COURSE_ID, 1)

            # Callback message edited with accepted text
            edits = _edits(bot)
            assert len(edits) >= 1
            assert "1/2" in edits[0].data.get("text", "")

            # Topic icon → 💊
            fe = _forum_edits(bot)
            assert any(
                str(TOPIC_ICON_ACTIVE) in str(r.data.get("icon_custom_emoji_id", ""))
                for r in fe
            )

            # Girl notified — first appeal message
            private = _private_sends(bot)
            assert len(private) == 1
            assert "ещё одна попытка" in private[0].data.get("text", "")

            # Card buttons restored (can_extend=True since not extended)
            btns = _card_button_texts(bot)
            assert "Продлить +21 день" in btns
            assert "Завершить программу" in btns

    async def test_happy_path_second_appeal(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, course=_course(status=CourseStatus.APPEAL, appeal_count=1))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _seed_reg_card(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            mocks.course_repo.accept_appeal.assert_called_once_with(COURSE_ID, 2)

            # Girl gets "last chance" message
            private = _private_sends(bot)
            assert len(private) == 1
            assert "последняя возможность" in private[0].data.get("text", "")

            # Topic text shows 2/2
            edits = _edits(bot)
            assert any("2/2" in e.data.get("text", "") for e in edits)

    async def test_callback_message_edited_removes_buttons(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _seed_reg_card(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            edits = _edits(bot)
            assert len(edits) >= 1
            # reply_markup should be None/empty (buttons removed)
            markup = edits[0].data.get("reply_markup")
            if markup and isinstance(markup, str):
                markup = json.loads(markup)
            assert not markup or not markup.get("inline_keyboard")

    async def test_callback_answer_sent(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1
            assert len(_alert_answers(bot)) == 0

    # ── Topic icon ────────────────────────────────────────────────────────

    async def test_topic_icon_changed_to_active(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            fe = _forum_edits(bot)
            assert len(fe) >= 1
            assert str(fe[0].data.get("icon_custom_emoji_id")) == str(TOPIC_ICON_ACTIVE)

    async def test_user_not_found_skips_icon(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, user=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            assert len(_forum_edits(bot)) == 0
            assert len(_private_sends(bot)) == 0
            assert len(_edit_markups(bot)) <= 1  # only callback edit

    async def test_user_no_topic_id_skips_icon(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, user=_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            assert len(_forum_edits(bot)) == 0

    async def test_icon_change_fails_silently(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "editForumTopic", 500)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            # Girl still notified
            assert len(_private_sends(bot)) == 1

    # ── Girl notification ─────────────────────────────────────────────────

    async def test_girl_notified(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, course=_course(status=CourseStatus.APPEAL, appeal_count=0))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            private = _private_sends(bot)
            assert len(private) == 1
            assert AppealTemplates.appeal_accepted(1) == private[0].data.get("text", "")

    async def test_user_no_telegram_id(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, user=_user(telegram_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            assert len(_private_sends(bot)) == 0

    async def test_girl_blocked_bot(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_for_chat(bot, "sendMessage", USER_ID, 403)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            # Callback still answered
            assert len(_answers(bot)) >= 1

    async def test_girl_dm_other_error(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_for_chat(bot, "sendMessage", USER_ID, 500)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            assert len(_answers(bot)) >= 1

    # ── Card buttons ──────────────────────────────────────────────────────

    async def test_card_buttons_restored(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, course=_course(status=CourseStatus.APPEAL, extended=False))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _seed_reg_card(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            btns = _card_button_texts(bot)
            assert "Продлить +21 день" in btns

    async def test_card_buttons_extended_course(self, mocks: MockHolder) -> None:
        _setup_accept(mocks, course=_course(status=CourseStatus.APPEAL, extended=True))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _seed_reg_card(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            btns = _card_button_texts(bot)
            assert "Продлить +21 день" not in btns
            assert "Завершить программу" in btns

    async def test_card_no_registration_message_id(self, mocks: MockHolder) -> None:
        _setup_accept(
            mocks,
            course=_course(status=CourseStatus.APPEAL, registration_message_id=None),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            # No editMessageReplyMarkup to GROUP
            group_markups = [
                r for r in _edit_markups(bot)
                if str(r.data.get("chat_id")) == _S_GROUP
            ]
            assert len(group_markups) == 0

    async def test_card_edit_bad_request_silent(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            # Don't seed reg card → edit will fail with 400
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            # Callback still answered
            assert len(_answers(bot)) >= 1

    async def test_card_edit_other_error_silent(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _seed_reg_card(bot)
            _fail_match(
                bot, "editMessageReplyMarkup", 500,
                chat_id=KOK_GROUP_ID, message_id=REG_MSG_ID,
            )
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            assert len(_answers(bot)) >= 1

    async def test_callback_edit_text_fails_silently(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "editMessageText", 400)
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            # Icon still changed despite edit failure
            assert len(_forum_edits(bot)) >= 1
            assert len(_answers(bot)) >= 1

    async def test_callback_message_none(self, mocks: MockHolder) -> None:
        _setup_accept(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await dp.feed_update(bot.bot, _make_callback_update(_accept_cb()))

            # No editMessageText (no message to edit)
            assert len(_edits(bot)) == 0

            # But icon and girl DM still work
            assert len(_forum_edits(bot)) >= 1
            assert len(_private_sends(bot)) == 1


# ══════════════════════════════════════════════════════════════════════════
# on_appeal_decline — Manager declines appeal
# ══════════════════════════════════════════════════════════════════════════


class TestOnAppealDecline:

    # ── Guards ────────────────────────────────────────────────────────────

    async def test_course_not_found(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1

    async def test_course_not_appeal_status(self, mocks: MockHolder) -> None:
        _setup_decline(mocks, course=_course(status=CourseStatus.REFUSED))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 1

    async def test_race_condition(self, mocks: MockHolder) -> None:
        _setup_decline(mocks, declined=False)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert AppealTemplates.appeal_already_handled() in alerts[0].data.get("text", "")

    # ── Happy path ────────────────────────────────────────────────────────

    async def test_happy_path(self, mocks: MockHolder) -> None:
        _setup_decline(mocks, course=_course(status=CourseStatus.APPEAL, appeal_count=0))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            # decline_appeal called with count=1
            mocks.course_repo.decline_appeal.assert_called_once_with(COURSE_ID, 1)

            # Callback message edited with declined text
            edits = _edits(bot)
            assert len(edits) >= 1
            assert "1/2" in edits[0].data.get("text", "")

            # Topic icon → ❗️
            fe = _forum_edits(bot)
            assert any(
                str(TOPIC_ICON_REFUSED) in str(r.data.get("icon_custom_emoji_id", ""))
                for r in fe
            )

            # Topic closed
            assert len(_forum_closes(bot)) == 1

            # Girl notified with manager name
            private = _private_sends(bot)
            assert len(private) == 1
            assert "Test Manager" in private[0].data.get("text", "")

    async def test_callback_message_edited_removes_buttons(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            edits = _edits(bot)
            assert len(edits) >= 1
            markup = edits[0].data.get("reply_markup")
            if markup and isinstance(markup, str):
                markup = json.loads(markup)
            assert not markup or not markup.get("inline_keyboard")

    async def test_callback_answer_sent(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)
            assert len(_answers(bot)) >= 1
            assert len(_alert_answers(bot)) == 0

    # ── Topic operations ──────────────────────────────────────────────────

    async def test_topic_icon_changed_to_refused(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            fe = _forum_edits(bot)
            assert len(fe) >= 1
            assert str(fe[0].data.get("icon_custom_emoji_id")) == str(TOPIC_ICON_REFUSED)

    async def test_topic_closed(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            closes = _forum_closes(bot)
            assert len(closes) == 1
            assert str(closes[0].data.get("chat_id")) == _S_GROUP
            assert str(closes[0].data.get("message_thread_id")) == str(TOPIC_ID)

    async def test_user_not_found_skips_topic_and_dm(self, mocks: MockHolder) -> None:
        _setup_decline(mocks, user=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            assert len(_forum_edits(bot)) == 0
            assert len(_forum_closes(bot)) == 0
            assert len(_private_sends(bot)) == 0

    async def test_user_no_topic_id_skips_topic(self, mocks: MockHolder) -> None:
        _setup_decline(mocks, user=_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            assert len(_forum_edits(bot)) == 0
            assert len(_forum_closes(bot)) == 0
            # But DM still sent (has telegram_id)
            assert len(_private_sends(bot)) == 1

    async def test_icon_change_fails_but_close_still_attempted(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "editForumTopic", 500)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            # Close still attempted despite icon failure
            assert len(_forum_closes(bot)) == 1

    async def test_close_topic_fails_silently(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "closeForumTopic", 500)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            # Girl still notified
            assert len(_private_sends(bot)) == 1

    # ── Girl notification ─────────────────────────────────────────────────

    async def test_girl_notified_with_manager_name(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            private = _private_sends(bot)
            assert len(private) == 1
            text = private[0].data.get("text", "")
            assert "Test Manager" in text
            assert AppealTemplates.appeal_declined("Test Manager") == text

    async def test_manager_not_found_fallback_name(self, mocks: MockHolder) -> None:
        _setup_decline(mocks, manager=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            private = _private_sends(bot)
            assert len(private) == 1
            # Fallback: "менеджер" instead of actual name
            assert "менеджер" in private[0].data.get("text", "")

    async def test_girl_blocked_bot(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_for_chat(bot, "sendMessage", USER_ID, 403)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            assert len(_answers(bot)) >= 1

    async def test_girl_dm_other_error(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_for_chat(bot, "sendMessage", USER_ID, 500)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            assert len(_answers(bot)) >= 1

    async def test_callback_edit_text_fails_silently(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "editMessageText", 400)
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            # Icon and close still happen
            assert len(_forum_edits(bot)) >= 1
            assert len(_forum_closes(bot)) == 1

    async def test_callback_message_none(self, mocks: MockHolder) -> None:
        _setup_decline(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            await dp.feed_update(bot.bot, _make_callback_update(_decline_cb()))

            # No editMessageText
            assert len(_edits(bot)) == 0

            # But icon, close, and girl DM still work
            assert len(_forum_edits(bot)) >= 1
            assert len(_forum_closes(bot)) == 1
            assert len(_private_sends(bot)) == 1


# ══════════════════════════════════════════════════════════════════════════
# Scenario Tests — full E2E flows through appeal handler
# ══════════════════════════════════════════════════════════════════════════


class TestScenarioNoVideoAppealAccepted:
    """Full flow: girl removed for no_video → appeal → accepted.

    Steps:
        1. Girl clicks "Апелляция" → FSM enters video state
        2. Girl sends video → FSM enters text state
        3. Girl sends text → appeal saved, topic reopened + icon ❓,
           video + review buttons sent to topic, manager DM + general topic
        4. Manager clicks "Принять" → course active, icon 💊,
           card buttons restored, girl notified
    """

    async def test_full_flow(self, mocks: MockHolder) -> None:
        course = _course(removal_reason="no_video", appeal_count=0)
        _setup_start(mocks, course=course)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _seed_reg_card(bot)

            # ── Step 1: Girl clicks "Апелляция" ──
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)

            # DB: start_appeal called
            mocks.course_repo.start_appeal.assert_called_once_with(COURSE_ID)
            # FSM → video state
            assert await _get_fsm_state(dp) == AppealStates.video.state
            # Girl received ask_video prompt
            p1 = _private_sends(bot)
            assert len(p1) == 1
            assert AppealTemplates.ask_video() in p1[0].data.get("text", "")
            # Appeal button removed from original message
            assert len(_edit_markups(bot)) >= 1
            # No alerts (successful start)
            assert len(_alert_answers(bot)) == 0

            # ── Step 2: Girl sends video ──
            bot._server.tracker.clear()
            await bot.send_video_note(file_id="appeal_video_123")

            # FSM → text state
            assert await _get_fsm_state(dp) == AppealStates.text.state
            fsm = await _get_fsm_data(dp)
            assert fsm["appeal_video"] == "appeal_video_123"
            assert fsm["course_id"] == COURSE_ID
            # Girl received ask_text prompt
            p2 = _private_sends(bot)
            assert any(AppealTemplates.ask_text() in m.data.get("text", "") for m in p2)

            # ── Step 3: Girl sends text ──
            bot._server.tracker.clear()
            _setup_text(mocks)
            await bot.send_message("Я пила таблетку, просто забыла снять видео")

            # DB: save_appeal_data called with video + text
            mocks.course_repo.save_appeal_data.assert_called_once_with(
                COURSE_ID, "appeal_video_123",
                "Я пила таблетку, просто забыла снять видео",
            )
            # FSM cleared
            assert await _get_fsm_state(dp) is None

            # Girl notified: appeal submitted
            p3 = _private_sends(bot)
            assert any(
                AppealTemplates.appeal_submitted() in m.data.get("text", "")
                for m in p3
            )

            # Topic reopened
            reopens = _forum_reopens(bot)
            assert len(reopens) == 1
            assert str(reopens[0].data.get("chat_id")) == _S_GROUP
            assert str(reopens[0].data.get("message_thread_id")) == str(TOPIC_ID)

            # Topic icon → ❓ (APPEAL)
            fe = _forum_edits(bot)
            assert any(
                str(r.data.get("icon_custom_emoji_id")) == str(TOPIC_ICON_APPEAL)
                for r in fe
            )

            # Video sent to topic
            vids = _videos_sent(bot)
            assert len(vids) == 1
            assert str(vids[0].data.get("chat_id")) == _S_GROUP
            assert str(vids[0].data.get("message_thread_id")) == str(TOPIC_ID)
            assert vids[0].data.get("video") == "appeal_video_123"

            # Text + review buttons sent to topic
            topic_msgs = _group_sends(bot, TOPIC_ID)
            assert len(topic_msgs) >= 1
            appeal_msg = topic_msgs[0]
            assert "Я пила таблетку" in appeal_msg.data.get("text", "")
            assert _has_review_buttons(appeal_msg.data)

            # Manager DM sent
            manager_dms = _manager_sends(bot)
            assert len(manager_dms) == 1
            assert "Проверь апелляцию" in manager_dms[0].data.get("text", "")
            assert DEADLINE_STR in manager_dms[0].data.get("text", "")

            # General topic notification
            general_msgs = _group_sends(bot, KOK_GENERAL_TOPIC_ID)
            assert len(general_msgs) == 1
            assert "Test Manager" in general_msgs[0].data.get("text", "")
            assert "Test Girl" in general_msgs[0].data.get("text", "")

            # ── Step 4: Manager clicks "Принять" ──
            bot._server.tracker.clear()
            _setup_accept(mocks)
            # Seed the review message in group so editMessageText works
            bot.chat_state.add_message(
                chat_id=KOK_GROUP_ID, from_user_id=BOT_ID, is_bot=True,
                text="appeal review", message_id=CALLBACK_MSG_ID,
                message_thread_id=TOPIC_ID,
            )
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            # DB: accept_appeal called with incremented count
            mocks.course_repo.accept_appeal.assert_called_once_with(COURSE_ID, 1)

            # Topic message edited: "Апелляция принята (1/2)"
            edits = _edits(bot)
            assert any(
                "Апелляция принята (1/2)" in e.data.get("text", "")
                for e in edits
            )

            # Topic icon → 💊 (ACTIVE)
            fe2 = _forum_edits(bot)
            assert any(
                str(r.data.get("icon_custom_emoji_id")) == str(TOPIC_ICON_ACTIVE)
                for r in fe2
            )

            # NO topic close (course reactivated)
            assert len(_forum_closes(bot)) == 0

            # Girl notified: appeal accepted (first appeal)
            p4 = _private_sends(bot)
            assert any(
                "ещё одна попытка" in m.data.get("text", "")
                for m in p4
            )

            # Registration card buttons restored
            markup_edits = _edit_markups(bot)
            group_markup_edits = [
                r for r in markup_edits
                if str(r.data.get("chat_id")) == _S_GROUP
                and str(r.data.get("message_id")) == str(REG_MSG_ID)
            ]
            assert len(group_markup_edits) == 1


class TestScenarioMaxStrikesAppealDeclined:
    """Full flow: girl removed for max_strikes → appeal → declined.

    Steps:
        1. Girl clicks "Апелляция" → FSM video
        2. Girl sends video → FSM text
        3. Girl sends text → appeal submitted
        4. Manager clicks "Отклонить" → course refused permanently,
           topic icon ❗ + close, girl notified
    """

    async def test_full_flow(self, mocks: MockHolder) -> None:
        course = _course(
            removal_reason="max_strikes", appeal_count=0,
            late_dates=["2025-01-10T10:30:00", "2025-01-11T10:30:00", "2025-01-12T10:30:00"],
            late_count=3,
        )
        _setup_start(mocks, course=course)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)

            # ── Step 1: Girl clicks "Апелляция" ──
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            mocks.course_repo.start_appeal.assert_called_once()
            assert await _get_fsm_state(dp) == AppealStates.video.state

            # ── Step 2: Girl sends video ──
            bot._server.tracker.clear()
            await bot.send_video(file_id="strikes_appeal_vid")
            assert await _get_fsm_state(dp) == AppealStates.text.state

            # ── Step 3: Girl sends text ──
            bot._server.tracker.clear()
            _setup_text(mocks)
            await bot.send_message("Я не опаздывала, часы врут")

            mocks.course_repo.save_appeal_data.assert_called_once_with(
                COURSE_ID, "strikes_appeal_vid", "Я не опаздывала, часы врут",
            )
            assert await _get_fsm_state(dp) is None

            # Appeal submitted to girl
            p3 = _private_sends(bot)
            assert any(
                AppealTemplates.appeal_submitted() in m.data.get("text", "")
                for m in p3
            )
            # Topic reopened and icon ❓
            assert len(_forum_reopens(bot)) == 1
            assert any(
                str(r.data.get("icon_custom_emoji_id")) == str(TOPIC_ICON_APPEAL)
                for r in _forum_edits(bot)
            )
            # Review buttons in topic
            topic_msgs = _group_sends(bot, TOPIC_ID)
            assert any(_has_review_buttons(m.data) for m in topic_msgs)

            # ── Step 4: Manager clicks "Отклонить" ──
            bot._server.tracker.clear()
            _setup_decline(mocks)
            bot.chat_state.add_message(
                chat_id=KOK_GROUP_ID, from_user_id=BOT_ID, is_bot=True,
                text="appeal review", message_id=CALLBACK_MSG_ID,
                message_thread_id=TOPIC_ID,
            )
            await bot.click_button(_decline_cb(), CALLBACK_MSG_ID)

            # DB: decline_appeal called
            mocks.course_repo.decline_appeal.assert_called_once_with(COURSE_ID, 1)

            # Topic message: "Апелляция отклонена (1/2)"
            edits = _edits(bot)
            assert any(
                "Апелляция отклонена (1/2)" in e.data.get("text", "")
                for e in edits
            )

            # Topic icon → ❗️ (REFUSED)
            fe = _forum_edits(bot)
            assert any(
                str(r.data.get("icon_custom_emoji_id")) == str(TOPIC_ICON_REFUSED)
                for r in fe
            )

            # Topic CLOSED
            closes = _forum_closes(bot)
            assert len(closes) == 1
            assert str(closes[0].data.get("chat_id")) == _S_GROUP
            assert str(closes[0].data.get("message_thread_id")) == str(TOPIC_ID)

            # Girl notified: appeal declined with manager name
            p4 = _private_sends(bot)
            assert any(
                "отклонил апелляцию" in m.data.get("text", "")
                and "Test Manager" in m.data.get("text", "")
                for m in p4
            )


class TestScenarioReshootExpiredNoAppeal:
    """Girl removed for reshoot_expired → clicks appeal → blocked.

    Verifies: no DB changes, no messages sent, no topic operations.
    """

    async def test_appeal_blocked(self, mocks: MockHolder) -> None:
        course = _course(removal_reason="reshoot_expired", appeal_count=0)
        _setup_start(mocks, course=course)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)

            # Alert shown
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert AppealTemplates.no_active_appeal() in alerts[0].data.get("text", "")

            # NO DB changes
            mocks.course_repo.start_appeal.assert_not_called()
            mocks.course_repo.save_appeal_data.assert_not_called()
            mocks.course_repo.accept_appeal.assert_not_called()

            # NO messages to girl (besides the alert)
            assert len(_private_sends(bot)) == 0

            # NO topic operations
            assert len(_forum_edits(bot)) == 0
            assert len(_forum_closes(bot)) == 0
            assert len(_forum_reopens(bot)) == 0
            assert len(_videos_sent(bot)) == 0

            # NO manager notifications
            assert len(_manager_sends(bot)) == 0
            assert len(_group_sends(bot, KOK_GENERAL_TOPIC_ID)) == 0

            # FSM NOT entered
            assert await _get_fsm_state(dp) is None


class TestScenarioManagerRejectNoAppeal:
    """Girl removed by manager_reject → clicks appeal → blocked.

    Verifies: identical to reshoot_expired — full block, no side effects.
    """

    async def test_appeal_blocked(self, mocks: MockHolder) -> None:
        course = _course(removal_reason="manager_reject", appeal_count=0)
        _setup_start(mocks, course=course)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)

            # Alert shown
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert AppealTemplates.no_active_appeal() in alerts[0].data.get("text", "")

            # NO DB changes
            mocks.course_repo.start_appeal.assert_not_called()

            # NO messages, NO topic ops, NO FSM
            assert len(_private_sends(bot)) == 0
            assert len(_forum_edits(bot)) == 0
            assert len(_forum_closes(bot)) == 0
            assert len(_forum_reopens(bot)) == 0
            assert len(_manager_sends(bot)) == 0
            assert await _get_fsm_state(dp) is None


class TestScenarioSecondAppealAfterAccept:
    """Girl used 1 appeal (accepted) → removed again for no_video → second appeal → accepted.

    Verifies: appeal_count=1 allows second appeal, girl gets "последняя возможность" text.
    """

    async def test_second_appeal_accepted(self, mocks: MockHolder) -> None:
        course = _course(
            removal_reason="no_video", appeal_count=1,
        )
        _setup_start(mocks, course=course)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)

            # ── Step 1: Girl clicks "Апелляция" (second time) ──
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)
            mocks.course_repo.start_appeal.assert_called_once()
            assert await _get_fsm_state(dp) == AppealStates.video.state

            # ── Step 2: Girl sends video ──
            bot._server.tracker.clear()
            await bot.send_video_note(file_id="second_appeal_vid")
            assert await _get_fsm_state(dp) == AppealStates.text.state

            # ── Step 3: Girl sends text ──
            bot._server.tracker.clear()
            _setup_text(mocks)
            await bot.send_message("Вторая апелляция, опять забыла")

            assert await _get_fsm_state(dp) is None
            mocks.course_repo.save_appeal_data.assert_called_once()

            # ── Step 4: Manager accepts second appeal ──
            bot._server.tracker.clear()
            _setup_accept(mocks, course=_course(
                status=CourseStatus.APPEAL, appeal_count=1,
            ))
            bot.chat_state.add_message(
                chat_id=KOK_GROUP_ID, from_user_id=BOT_ID, is_bot=True,
                text="appeal review", message_id=CALLBACK_MSG_ID,
                message_thread_id=TOPIC_ID,
            )
            await bot.click_button(_accept_cb(), CALLBACK_MSG_ID)

            # DB: accept_appeal with count=2
            mocks.course_repo.accept_appeal.assert_called_once_with(COURSE_ID, 2)

            # Topic message: "Апелляция принята (2/2)"
            edits = _edits(bot)
            assert any(
                "Апелляция принята (2/2)" in e.data.get("text", "")
                for e in edits
            )

            # Girl gets "последняя возможность" warning
            p4 = _private_sends(bot)
            assert any(
                "последняя возможность" in m.data.get("text", "")
                for m in p4
            )


class TestScenarioThirdAppealBlocked:
    """Girl already used 2 appeals → removed again → clicks appeal → blocked (max reached)."""

    async def test_max_appeals_exhausted(self, mocks: MockHolder) -> None:
        course = _course(removal_reason="no_video", appeal_count=2)
        _setup_start(mocks, course=course)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_start_cb(), CALLBACK_MSG_ID)

            # Alert shown — max appeals
            alerts = _alert_answers(bot)
            assert len(alerts) == 1

            # NO DB changes, NO FSM
            mocks.course_repo.start_appeal.assert_not_called()
            assert await _get_fsm_state(dp) is None

            # NO messages, NO topic ops
            assert len(_private_sends(bot)) == 0
            assert len(_forum_edits(bot)) == 0
