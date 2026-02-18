"""Tests for handlers/card.py — 55 tests, 100% branch coverage."""
from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any

import pytest
from aiogram.types import CallbackQuery, Update
from aiogram.types import User as TgUser

from callbacks.card import CardAction, CardCallback
from handlers.card import EXTENSION_DAYS, TOPIC_ICON_COMPLETED
from models.course import Course
from models.enums import CourseStatus
from models.manager import Manager
from models.user import User as KokUser
from templates import CardTemplates
from tests.handlers.conftest import (
    KOK_GROUP_ID,
    MockHolder,
    create_test_dispatcher,
)
from tests.mock_server import MockTelegramBot
from tests.mock_server.tracker import TrackedRequest

# ── Constants ─────────────────────────────────────────────────────────────

BOT_ID = 1234567890
USER_ID = 123456789
MANAGER_TG_ID = 999999
TOPIC_ID = 42
COURSE_ID = 10
CALLBACK_MSG_ID = 1

_S_GROUP = str(KOK_GROUP_ID)


# ── Factories ─────────────────────────────────────────────────────────────


def _user(**ov: Any) -> KokUser:
    d: dict[str, Any] = dict(
        id=1, telegram_id=USER_ID, name="Ivanova Anna Petrovna",
        manager_id=1, topic_id=TOPIC_ID,
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return KokUser(**d)


def _course(**ov: Any) -> Course:
    d: dict[str, Any] = dict(
        id=COURSE_ID, user_id=1, status=CourseStatus.ACTIVE,
        intake_time=time(10, 0), current_day=5, total_days=21,
        late_count=0, appeal_count=0, late_dates=[], extended=False,
        registration_message_id=100,
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return Course(**d)


def _manager(**ov: Any) -> Manager:
    d: dict[str, Any] = dict(
        id=1, telegram_id=MANAGER_TG_ID, name="Test Manager",
        is_active=True, created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return Manager(**d)


# ── Callback data ─────────────────────────────────────────────────────────


def _extend_cb(course_id: int = COURSE_ID) -> str:
    return CardCallback(action=CardAction.EXTEND, course_id=course_id).pack()


def _complete_cb(course_id: int = COURSE_ID) -> str:
    return CardCallback(action=CardAction.COMPLETE, course_id=course_id).pack()


# ── Mock setup ────────────────────────────────────────────────────────────


def _setup_extend(m: MockHolder, **kw: Any) -> None:
    m.course_repo.get_by_id.return_value = kw.get("course", _course())
    m.course_repo.extend_course.return_value = kw.get("extended", True)
    m.user_repo.get_by_id.return_value = kw.get("user", _user())
    m.manager_repo.get_by_id.return_value = kw.get("manager", _manager())


def _setup_complete(m: MockHolder, **kw: Any) -> None:
    m.course_repo.get_by_id.return_value = kw.get("course", _course())
    m.course_repo.complete_course_active.return_value = kw.get("completed", True)
    m.user_repo.get_by_id.return_value = kw.get("user", _user())


# ── Tracker helpers ───────────────────────────────────────────────────────


def _sends(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("sendMessage")


def _private_sends(bot: MockTelegramBot) -> list[TrackedRequest]:
    return [r for r in _sends(bot) if str(r.data.get("chat_id")) == str(USER_ID)]


def _group_sends(
    bot: MockTelegramBot, topic_id: int | None = None,
) -> list[TrackedRequest]:
    out = []
    for r in _sends(bot):
        if str(r.data.get("chat_id")) == _S_GROUP:
            if topic_id is None or str(r.data.get("message_thread_id")) == str(topic_id):
                out.append(r)
    return out


def _edit_markups(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("editMessageReplyMarkup")


def _forum_edits(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("editForumTopic")


def _forum_closes(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("closeForumTopic")


def _answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("answerCallbackQuery")


def _is_alert(r: TrackedRequest) -> bool:
    return str(r.data.get("show_alert", "")).lower() in ("true", "1")


def _alert_answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return [r for r in _answers(bot) if _is_alert(r)]


def _non_alert_answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return [r for r in _answers(bot) if not _is_alert(r)]


def _keyboard_button_texts(bot: MockTelegramBot) -> list[str]:
    """Get button texts from editMessageReplyMarkup."""
    for r in _edit_markups(bot):
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


def _keyboard_markup_removed(bot: MockTelegramBot) -> bool:
    """Check if editMessageReplyMarkup was called with empty reply_markup."""
    for r in _edit_markups(bot):
        markup = r.data.get("reply_markup")
        if not markup:
            return True
    return False


# ── Seed / Fail helpers ──────────────────────────────────────────────────


def _seed(bot: MockTelegramBot) -> None:
    """Pre-add callback message so edits work on mock server."""
    bot.chat_state.add_message(
        chat_id=bot.chat_id, from_user_id=BOT_ID, is_bot=True,
        text="registration card", message_id=CALLBACK_MSG_ID,
    )


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
# on_extend — Manager clicks "Продлить +21 день"
# ══════════════════════════════════════════════════════════════════════════


class TestOnExtend:
    """31 tests for on_extend handler."""

    # ── Guards ────────────────────────────────────────────────────────

    async def test_course_not_found(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert CardTemplates.course_not_active() in alerts[0].data.get("text", "")

    async def test_course_not_active(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = _course(status=CourseStatus.REFUSED)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert CardTemplates.course_not_active() in alerts[0].data.get("text", "")

    async def test_already_extended(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = _course(extended=True)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert CardTemplates.already_extended() in alerts[0].data.get("text", "")

    async def test_race_condition_extend_course_false(self, mocks: MockHolder) -> None:
        _setup_extend(mocks, extended=False)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert CardTemplates.already_handled() in alerts[0].data.get("text", "")

    # ── Happy path ───────────────────────────────────────────────────

    async def test_happy_path(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            # No alert answers
            assert len(_alert_answers(bot)) == 0
            # Non-alert answer (final callback.answer())
            assert len(_non_alert_answers(bot)) == 1
            # Topic notification sent
            topic_msgs = _group_sends(bot, TOPIC_ID)
            assert len(topic_msgs) >= 1
            # Girl DM sent
            assert len(_private_sends(bot)) == 1

    async def test_extend_course_called_correctly(self, mocks: MockHolder) -> None:
        _setup_extend(mocks, course=_course(total_days=30))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            mocks.course_repo.extend_course.assert_called_once_with(
                COURSE_ID, 30 + EXTENSION_DAYS,
            )

    async def test_callback_answer_no_alert(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            non_alerts = _non_alert_answers(bot)
            assert len(non_alerts) == 1
            # No text in final answer
            assert not non_alerts[0].data.get("text")

    # ── Keyboard ─────────────────────────────────────────────────────

    async def test_keyboard_updated_can_extend_false(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            texts = _keyboard_button_texts(bot)
            # Only "Завершить" button should remain, no "Продлить"
            assert "Завершить программу" in texts
            assert "Продлить +21 день" not in texts

    async def test_callback_message_none_skips_edit(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            update = _make_callback_update(_extend_cb())
            await dp.feed_update(bot.bot, update)
            # No editMessageReplyMarkup calls
            assert len(_edit_markups(bot)) == 0
            # But rest of the flow still works
            assert len(_non_alert_answers(bot)) == 1

    async def test_edit_reply_markup_fails_silently(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "editMessageReplyMarkup", error_code=400)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            # Flow continues despite edit failure
            assert len(_group_sends(bot, TOPIC_ID)) >= 1
            assert len(_private_sends(bot)) == 1

    # ── Topic notification ───────────────────────────────────────────

    async def test_topic_message_sent(self, mocks: MockHolder) -> None:
        _setup_extend(mocks, course=_course(total_days=21))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            topic_msgs = _group_sends(bot, TOPIC_ID)
            assert len(topic_msgs) >= 1
            text = topic_msgs[0].data.get("text", "")
            assert CardTemplates.topic_extended(21, 21 + EXTENSION_DAYS) in text

    async def test_user_not_found_skips_topic_and_dm(self, mocks: MockHolder) -> None:
        _setup_extend(mocks, user=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            assert len(_group_sends(bot, TOPIC_ID)) == 0
            assert len(_private_sends(bot)) == 0
            assert len(_non_alert_answers(bot)) == 1

    async def test_user_no_topic_id_skips_topic(self, mocks: MockHolder) -> None:
        _setup_extend(mocks, user=_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            assert len(_group_sends(bot)) == 0
            assert len(_forum_edits(bot)) == 0
            # Girl DM still sent
            assert len(_private_sends(bot)) == 1

    async def test_topic_message_fails_silently(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_match(
                bot, "sendMessage", error_code=500,
                chat_id=KOK_GROUP_ID, message_thread_id=TOPIC_ID,
            )
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            # Topic name update still attempted
            assert len(_forum_edits(bot)) >= 1
            # Girl DM still sent
            assert len(_private_sends(bot)) == 1

    # ── Topic name ───────────────────────────────────────────────────

    async def test_topic_name_updated(self, mocks: MockHolder) -> None:
        _setup_extend(mocks, course=_course(current_day=5, total_days=21))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            assert len(edits) == 1
            name = edits[0].data.get("name", "")
            new_total = 21 + EXTENSION_DAYS
            assert f"5/{new_total}" in name

    async def test_topic_name_with_patronymic(self, mocks: MockHolder) -> None:
        """Full name: 'Ivanova Anna Petrovna' → 'Ivanova A.P. (Manager) 5/42'."""
        _setup_extend(mocks, user=_user(name="Ivanova Anna Petrovna"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            assert len(edits) == 1
            name = edits[0].data.get("name", "")
            assert "Ivanova A.P." in name

    async def test_topic_name_without_patronymic(self, mocks: MockHolder) -> None:
        """Full name: 'Ivanova Anna' → 'Ivanova A. (Manager) 5/42'."""
        _setup_extend(mocks, user=_user(name="Ivanova Anna"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            name = edits[0].data.get("name", "")
            assert "Ivanova A." in name
            assert "A.." not in name  # No double dot

    async def test_topic_name_single_word(self, mocks: MockHolder) -> None:
        """Full name: 'Ivanova' → 'Ivanova (Manager) 5/42'."""
        _setup_extend(mocks, user=_user(name="Ivanova"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            name = edits[0].data.get("name", "")
            assert "Ivanova" in name
            assert "(Test Manager)" in name

    async def test_topic_name_user_name_empty(self, mocks: MockHolder) -> None:
        """Empty name: '' → 'Unknown (Manager) 5/42'."""
        _setup_extend(mocks, user=_user(name=""))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            name = edits[0].data.get("name", "")
            assert "Unknown" in name

    async def test_topic_name_manager_not_found_fallback(self, mocks: MockHolder) -> None:
        """manager_repo returns None → manager_name = '?'."""
        _setup_extend(mocks, manager=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            name = edits[0].data.get("name", "")
            assert "(?)" in name

    async def test_edit_forum_topic_fails_silently(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "editForumTopic", error_code=500)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            # Flow continues — girl DM still sent
            assert len(_private_sends(bot)) == 1
            assert len(_non_alert_answers(bot)) == 1

    async def test_topic_name_only_kizi_suffix(self, mocks: MockHolder) -> None:
        """Name: 'Ivanova Anna kizi' → patron='kizi', clean=[] → no patron initial."""
        _setup_extend(mocks, user=_user(name="Ivanova Anna kizi"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            name = edits[0].data.get("name", "")
            # Should be "Ivanova A." — no patron initial since kizi is removed
            assert "Ivanova A." in name
            assert "A.k" not in name.lower()

    async def test_topic_name_kizi_with_patronymic(self, mocks: MockHolder) -> None:
        """Name: 'Ivanova Anna Rustam kizi' → patron='Rustam kizi', clean=['Rustam'] → R."""
        _setup_extend(mocks, user=_user(name="Ivanova Anna Rustam kizi"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            name = edits[0].data.get("name", "")
            assert "Ivanova A.R." in name

    async def test_current_day_in_topic_name(self, mocks: MockHolder) -> None:
        """current_day=12 should appear in topic name."""
        _setup_extend(mocks, course=_course(current_day=12, total_days=21))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            name = edits[0].data.get("name", "")
            assert f"12/{21 + EXTENSION_DAYS}" in name

    # ── Girl DM ──────────────────────────────────────────────────────

    async def test_girl_notified(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            dm = _private_sends(bot)
            assert len(dm) == 1
            assert CardTemplates.private_extended() in dm[0].data.get("text", "")

    async def test_user_no_telegram_id(self, mocks: MockHolder) -> None:
        _setup_extend(mocks, user=_user(telegram_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            assert len(_private_sends(bot)) == 0
            # But topic ops still work
            assert len(_group_sends(bot, TOPIC_ID)) >= 1

    async def test_girl_blocked_bot(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_for_chat(bot, "sendMessage", USER_ID, error_code=403)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            # Flow completes despite blocked bot
            assert len(_non_alert_answers(bot)) == 1

    async def test_girl_dm_other_error(self, mocks: MockHolder) -> None:
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_for_chat(bot, "sendMessage", USER_ID, error_code=500)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            # Flow completes despite generic error
            assert len(_non_alert_answers(bot)) == 1

    # ── Edge cases ───────────────────────────────────────────────────

    async def test_custom_total_days(self, mocks: MockHolder) -> None:
        """Course with non-default total_days=30 → extend to 51."""
        _setup_extend(mocks, course=_course(total_days=30))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            topic_msgs = _group_sends(bot, TOPIC_ID)
            text = topic_msgs[0].data.get("text", "")
            assert CardTemplates.topic_extended(30, 30 + EXTENSION_DAYS) in text

    async def test_topic_name_qizi_variant(self, mocks: MockHolder) -> None:
        """Name: 'Ivanova Anna Rustam qizi' → qizi removed same as kizi."""
        _setup_extend(mocks, user=_user(name="Ivanova Anna Rustam qizi"))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_extend_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            name = edits[0].data.get("name", "")
            assert "Ivanova A.R." in name

    async def test_callback_message_none_full_flow(self, mocks: MockHolder) -> None:
        """callback.message=None: skip edit, but topic + DM still work."""
        _setup_extend(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            update = _make_callback_update(_extend_cb())
            await dp.feed_update(bot.bot, update)
            assert len(_edit_markups(bot)) == 0
            assert len(_group_sends(bot, TOPIC_ID)) >= 1
            assert len(_forum_edits(bot)) == 1
            assert len(_private_sends(bot)) == 1


# ══════════════════════════════════════════════════════════════════════════
# on_complete — Manager clicks "Завершить программу"
# ══════════════════════════════════════════════════════════════════════════


class TestOnComplete:
    """24 tests for on_complete handler."""

    # ── Guards ────────────────────────────────────────────────────────

    async def test_course_not_found(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert CardTemplates.course_not_active() in alerts[0].data.get("text", "")

    async def test_course_not_active(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = _course(status=CourseStatus.COMPLETED)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert CardTemplates.course_not_active() in alerts[0].data.get("text", "")

    async def test_race_condition_complete_false(self, mocks: MockHolder) -> None:
        _setup_complete(mocks, completed=False)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert CardTemplates.already_handled() in alerts[0].data.get("text", "")

    # ── Happy path ───────────────────────────────────────────────────

    async def test_happy_path(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            assert len(_alert_answers(bot)) == 0
            assert len(_non_alert_answers(bot)) == 1
            assert len(_group_sends(bot, TOPIC_ID)) >= 1
            assert len(_private_sends(bot)) == 1

    async def test_complete_course_called(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            mocks.course_repo.complete_course_active.assert_called_once_with(COURSE_ID)

    async def test_callback_answer_no_alert(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            non_alerts = _non_alert_answers(bot)
            assert len(non_alerts) == 1
            assert not non_alerts[0].data.get("text")

    # ── Keyboard ─────────────────────────────────────────────────────

    async def test_keyboard_removed(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            assert _keyboard_markup_removed(bot)

    async def test_callback_message_none_skips_edit(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            update = _make_callback_update(_complete_cb())
            await dp.feed_update(bot.bot, update)
            assert len(_edit_markups(bot)) == 0
            assert len(_non_alert_answers(bot)) == 1

    async def test_edit_reply_markup_fails_silently(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "editMessageReplyMarkup", error_code=400)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            # Flow continues
            assert len(_group_sends(bot, TOPIC_ID)) >= 1
            assert len(_private_sends(bot)) == 1

    # ── Topic operations ─────────────────────────────────────────────

    async def test_topic_message_sent(self, mocks: MockHolder) -> None:
        _setup_complete(mocks, course=_course(current_day=7, total_days=21))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            topic_msgs = _group_sends(bot, TOPIC_ID)
            assert len(topic_msgs) >= 1
            text = topic_msgs[0].data.get("text", "")
            assert CardTemplates.topic_completed_early(7, 21) in text

    async def test_topic_icon_changed(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            edits = _forum_edits(bot)
            assert len(edits) == 1
            assert edits[0].data.get("icon_custom_emoji_id") == str(TOPIC_ICON_COMPLETED)

    async def test_topic_closed(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            closes = _forum_closes(bot)
            assert len(closes) == 1
            assert str(closes[0].data.get("chat_id")) == _S_GROUP
            assert str(closes[0].data.get("message_thread_id")) == str(TOPIC_ID)

    async def test_user_not_found_skips_all(self, mocks: MockHolder) -> None:
        _setup_complete(mocks, user=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            assert len(_group_sends(bot, TOPIC_ID)) == 0
            assert len(_forum_edits(bot)) == 0
            assert len(_forum_closes(bot)) == 0
            assert len(_private_sends(bot)) == 0
            assert len(_non_alert_answers(bot)) == 1

    async def test_user_no_topic_id_skips_all_topic_ops(self, mocks: MockHolder) -> None:
        _setup_complete(mocks, user=_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            assert len(_group_sends(bot)) == 0
            assert len(_forum_edits(bot)) == 0
            assert len(_forum_closes(bot)) == 0
            # Girl DM still sent
            assert len(_private_sends(bot)) == 1

    async def test_topic_message_fails_icon_and_close_work(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_match(
                bot, "sendMessage", error_code=500,
                chat_id=KOK_GROUP_ID, message_thread_id=TOPIC_ID,
            )
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            # Icon and close still attempted despite sendMessage failure
            assert len(_forum_edits(bot)) == 1
            assert len(_forum_closes(bot)) == 1

    async def test_icon_fails_close_works(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "editForumTopic", error_code=500)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            # Close still attempted despite icon failure
            assert len(_forum_closes(bot)) == 1
            assert len(_private_sends(bot)) == 1

    async def test_close_fails_silently(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail(bot, "closeForumTopic", error_code=500)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            # Flow continues — girl DM still sent
            assert len(_private_sends(bot)) == 1
            assert len(_non_alert_answers(bot)) == 1

    # ── Girl DM ──────────────────────────────────────────────────────

    async def test_girl_notified(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            dm = _private_sends(bot)
            assert len(dm) == 1
            assert CardTemplates.private_completed_early() in dm[0].data.get("text", "")

    async def test_user_no_telegram_id(self, mocks: MockHolder) -> None:
        _setup_complete(mocks, user=_user(telegram_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            assert len(_private_sends(bot)) == 0
            # Topic ops still work
            assert len(_group_sends(bot, TOPIC_ID)) >= 1

    async def test_girl_blocked_bot(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_for_chat(bot, "sendMessage", USER_ID, error_code=403)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            assert len(_non_alert_answers(bot)) == 1

    async def test_girl_dm_other_error(self, mocks: MockHolder) -> None:
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            _fail_for_chat(bot, "sendMessage", USER_ID, error_code=500)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            assert len(_non_alert_answers(bot)) == 1

    # ── Edge cases ───────────────────────────────────────────────────

    async def test_current_day_total_in_message(self, mocks: MockHolder) -> None:
        """current_day and total_days appear in topic message."""
        _setup_complete(mocks, course=_course(current_day=15, total_days=42))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            topic_msgs = _group_sends(bot, TOPIC_ID)
            text = topic_msgs[0].data.get("text", "")
            assert "15" in text
            assert "42" in text

    async def test_all_topic_ops_attempted(self, mocks: MockHolder) -> None:
        """Verify all 3 topic operations: sendMessage, editForumTopic, closeForumTopic."""
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            _seed(bot)
            await bot.click_button(_complete_cb(), CALLBACK_MSG_ID)
            assert len(_group_sends(bot, TOPIC_ID)) >= 1
            assert len(_forum_edits(bot)) == 1
            assert len(_forum_closes(bot)) == 1

    async def test_callback_message_none_full_flow(self, mocks: MockHolder) -> None:
        """callback.message=None: skip edit, but topic ops + DM still work."""
        _setup_complete(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, user_id=USER_ID) as bot:
            update = _make_callback_update(_complete_cb())
            await dp.feed_update(bot.bot, update)
            assert len(_edit_markups(bot)) == 0
            assert len(_group_sends(bot, TOPIC_ID)) >= 1
            assert len(_forum_edits(bot)) == 1
            assert len(_forum_closes(bot)) == 1
            assert len(_private_sends(bot)) == 1
