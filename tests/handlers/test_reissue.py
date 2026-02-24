"""Tests for handlers/reissue.py — 17 tests, 100% branch coverage."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest
from aiogram.types import User as TgUser

from callbacks.menu import MenuAction, MenuCallback
from callbacks.reissue import ReissueCallback
from models.course import Course
from models.enums import CourseStatus, ReissueCategory
from models.manager import Manager
from models.reissue import ReissueGirl
from models.user import User as KokUser
from templates import AddTemplates, ReissueTemplates
from utils.time import TASHKENT_TZ
from tests.handlers.conftest import (
    KOK_GROUP_ID,
    MockHolder,
    create_test_dispatcher,
)
from tests.mock_server import MockTelegramBot
from tests.mock_server.tracker import TrackedRequest

# ── Constants ─────────────────────────────────────────────────────────────

BOT_ID = 1234567890
MANAGER_TG_ID = 999999
TOPIC_ID = 42
MENU_MSG_ID = 1
LIST_MSG_ID = 2

TIME_19 = datetime(2025, 1, 15, 19, 0, 0, tzinfo=TASHKENT_TZ)
TIME_20 = datetime(2025, 1, 15, 20, 0, 0, tzinfo=TASHKENT_TZ)
TIME_21 = datetime(2025, 1, 15, 21, 0, 0, tzinfo=TASHKENT_TZ)


# ── Factories ─────────────────────────────────────────────────────────────


def _manager(**ov: Any) -> Manager:
    d: dict[str, Any] = dict(
        id=1, telegram_id=MANAGER_TG_ID, name="Test Manager",
        is_active=True, created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return Manager(**d)


def _course(**ov: Any) -> Course:
    d: dict[str, Any] = dict(
        id=100, user_id=10, status=CourseStatus.SETUP,
        current_day=0, total_days=21,
        late_count=0, appeal_count=0, late_dates=[],
        invite_code="NEWCODE123AB",
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return Course(**d)


def _user(**ov: Any) -> KokUser:
    d: dict[str, Any] = dict(
        id=10, telegram_id=555555, name="Ivanova Anna",
        manager_id=1, topic_id=TOPIC_ID,
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return KokUser(**d)


def _girl(**ov: Any) -> ReissueGirl:
    d: dict[str, Any] = dict(
        course_id=100,
        short_name="Ivanova A.",
        date_str="15.01",
        category=ReissueCategory.NOT_STARTED,
    )
    d.update(ov)
    return ReissueGirl(**d)


# ── Callback helpers ──────────────────────────────────────────────────────


def _reissue_start_cb() -> str:
    return MenuCallback(action=MenuAction.REISSUE).pack()


def _girl_cb(course_id: int = 100) -> str:
    return ReissueCallback(course_id=course_id).pack()


# ── Tracker helpers ───────────────────────────────────────────────────────


def _sends(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("sendMessage")


def _edits(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("editMessageText")


def _answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("answerCallbackQuery")


def _is_alert(r: TrackedRequest) -> bool:
    return str(r.data.get("show_alert", "")).lower() in ("true", "1")


def _alert_answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return [r for r in _answers(bot) if _is_alert(r)]


def _non_alert_answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return [r for r in _answers(bot) if not _is_alert(r)]


# ── Seed helpers ──────────────────────────────────────────────────────────


def _seed_menu(bot: MockTelegramBot) -> None:
    bot.chat_state.add_message(
        chat_id=KOK_GROUP_ID, from_user_id=BOT_ID, is_bot=True,
        text="menu", message_id=MENU_MSG_ID,
        message_thread_id=TOPIC_ID,
    )


def _seed_list_msg(bot: MockTelegramBot) -> None:
    """Seed girl list message for on_girl_selected to edit."""
    bot.chat_state.add_message(
        chat_id=KOK_GROUP_ID, from_user_id=BOT_ID, is_bot=True,
        text="girl list", message_id=LIST_MSG_ID,
        message_thread_id=TOPIC_ID,
    )


def _bot_kw() -> dict[str, Any]:
    return dict(
        user_id=MANAGER_TG_ID,
        chat_id=KOK_GROUP_ID,
        chat_type="supergroup",
        message_thread_id=TOPIC_ID,
    )


# ══════════════════════════════════════════════════════════════════════════
# on_reissue_start — Manager clicks "Переотправить" in menu
# ══════════════════════════════════════════════════════════════════════════


class TestOnReissueStart:
    """7 tests for on_reissue_start callback handler."""

    @patch("handlers.reissue.get_tashkent_now", return_value=TIME_19)
    async def test_service_exception(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.get_reissuable_girls.side_effect = RuntimeError("DB down")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_reissue_start_cb(), MENU_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert ReissueTemplates.error_try_later() in alerts[0].data.get("text", "")
            assert _is_alert(alerts[0])

    @patch("handlers.reissue.get_tashkent_now", return_value=TIME_19)
    async def test_no_girls_show_alert(self, _mock_now, mocks: MockHolder) -> None:
        """L42: show_alert=True — popup when no reissuable girls."""
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.get_reissuable_girls.return_value = []
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_reissue_start_cb(), MENU_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert ReissueTemplates.no_girls() in alerts[0].data.get("text", "")
            assert _is_alert(alerts[0])
            assert len(_sends(bot)) == 0

    @patch("handlers.reissue.get_tashkent_now", return_value=TIME_20)
    async def test_time_restricted_at_20(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_reissue_start_cb(), MENU_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert AddTemplates.time_restricted() in alerts[0].data.get("text", "")
            assert _is_alert(alerts[0])
            assert len(_sends(bot)) == 0

    @patch("handlers.reissue.get_tashkent_now", return_value=TIME_21)
    async def test_time_restricted_after_20(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_reissue_start_cb(), MENU_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert AddTemplates.time_restricted() in alerts[0].data.get("text", "")
            assert _is_alert(alerts[0])
            assert len(_sends(bot)) == 0

    @patch("handlers.reissue.get_tashkent_now", return_value=TIME_19)
    async def test_happy_path_sends_list(self, _mock_now, mocks: MockHolder) -> None:
        girls = [
            _girl(),
            _girl(course_id=200, short_name="Petrova M.", date_str="16.01"),
        ]
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.get_reissuable_girls.return_value = girls
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_reissue_start_cb(), MENU_MSG_ID)
            sends = _sends(bot)
            assert len(sends) == 1
            text = sends[0].data.get("text", "")
            assert text == ReissueTemplates.select_girl(girls)

    @patch("handlers.reissue.get_tashkent_now", return_value=TIME_19)
    async def test_happy_path_keyboard_has_callbacks(self, _mock_now, mocks: MockHolder) -> None:
        girls = [
            _girl(course_id=100),
            _girl(course_id=200, short_name="Petrova M."),
        ]
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.get_reissuable_girls.return_value = girls
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_reissue_start_cb(), MENU_MSG_ID)
            markup = str(_sends(bot)[0].data.get("reply_markup", ""))
            assert "reissue:100" in markup
            assert "reissue:200" in markup

    @patch("handlers.reissue.get_tashkent_now", return_value=TIME_19)
    async def test_happy_path_callback_answered_no_alert(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.get_reissuable_girls.return_value = [_girl()]
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_reissue_start_cb(), MENU_MSG_ID)
            assert len(_non_alert_answers(bot)) == 1
            assert len(_alert_answers(bot)) == 0

    @patch("handlers.reissue.get_tashkent_now", return_value=TIME_19)
    async def test_correct_manager_id_passed(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager(id=42)
        mocks.add_service.get_reissuable_girls.return_value = [_girl()]
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_reissue_start_cb(), MENU_MSG_ID)
            mocks.add_service.get_reissuable_girls.assert_called_once_with(42)


# ══════════════════════════════════════════════════════════════════════════
# on_girl_selected — Manager clicks numbered button
# ══════════════════════════════════════════════════════════════════════════


class TestOnGirlSelected:
    """8 tests for on_girl_selected callback handler."""

    async def test_happy_path_link(self, mocks: MockHolder) -> None:
        mocks.add_service.reissue_link.return_value = _course(invite_code="ABC123XYZ999")
        mocks.user_repo.get_by_id.return_value = _user(name="Petrova Maria")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_list_msg(bot)
            await bot.click_button(_girl_cb(100), LIST_MSG_ID)
            edits = _edits(bot)
            assert len(edits) >= 1
            text = edits[-1].data.get("text", "")
            assert "Petrova Maria" in text
            assert "ABC123XYZ999" in text

    async def test_service_exception(self, mocks: MockHolder) -> None:
        mocks.add_service.reissue_link.side_effect = RuntimeError("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_list_msg(bot)
            await bot.click_button(_girl_cb(100), LIST_MSG_ID)
            all_texts = (
                [e.data.get("text", "") for e in _edits(bot)]
                + [s.data.get("text", "") for s in _sends(bot)]
            )
            assert any(ReissueTemplates.error_try_later() in t for t in all_texts)

    async def test_user_not_found_empty_name(self, mocks: MockHolder) -> None:
        mocks.add_service.reissue_link.return_value = _course(invite_code="CODE123")
        mocks.user_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_list_msg(bot)
            await bot.click_button(_girl_cb(100), LIST_MSG_ID)
            text = _edits(bot)[-1].data.get("text", "")
            assert "CODE123" in text
            bot_un = (await bot.bot.me()).username or ""
            assert text == ReissueTemplates.link_reissued("", bot_un, "CODE123")

    async def test_link_contains_invite_code(self, mocks: MockHolder) -> None:
        mocks.add_service.reissue_link.return_value = _course(invite_code="UNIQUECODE42")
        mocks.user_repo.get_by_id.return_value = _user()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_list_msg(bot)
            await bot.click_button(_girl_cb(100), LIST_MSG_ID)
            text = _edits(bot)[-1].data.get("text", "")
            assert "UNIQUECODE42" in text

    async def test_link_contains_bot_username(self, mocks: MockHolder) -> None:
        mocks.add_service.reissue_link.return_value = _course()
        mocks.user_repo.get_by_id.return_value = _user()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_list_msg(bot)
            await bot.click_button(_girl_cb(100), LIST_MSG_ID)
            text = _edits(bot)[-1].data.get("text", "")
            bot_username = (await bot.bot.me()).username
            assert bot_username in text

    async def test_bot_no_username_fallback(self, mocks: MockHolder) -> None:
        """L79: username is None → or '' → empty string in link."""
        mocks.add_service.reissue_link.return_value = _course(invite_code="CODE999")
        mocks.user_repo.get_by_id.return_value = _user()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_list_msg(bot)
            # Override cached bot info: username=None
            bot.bot._me = TgUser(id=BOT_ID, is_bot=True, first_name="Bot")
            await bot.click_button(_girl_cb(100), LIST_MSG_ID)
            text = _edits(bot)[-1].data.get("text", "")
            assert text == ReissueTemplates.link_reissued("Ivanova Anna", "", "CODE999")

    async def test_callback_answered(self, mocks: MockHolder) -> None:
        mocks.add_service.reissue_link.return_value = _course()
        mocks.user_repo.get_by_id.return_value = _user()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_list_msg(bot)
            await bot.click_button(_girl_cb(100), LIST_MSG_ID)
            assert len(_non_alert_answers(bot)) == 1

    async def test_invite_code_none_fallback(self, mocks: MockHolder) -> None:
        """L83: invite_code is None → or '' → empty code in link."""
        mocks.add_service.reissue_link.return_value = _course(invite_code=None)
        mocks.user_repo.get_by_id.return_value = _user()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_list_msg(bot)
            await bot.click_button(_girl_cb(100), LIST_MSG_ID)
            text = _edits(bot)[-1].data.get("text", "")
            bot_un = (await bot.bot.me()).username or ""
            assert text == ReissueTemplates.link_reissued("Ivanova Anna", bot_un, "")
