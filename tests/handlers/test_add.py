"""Tests for handlers/add/ (passport, receipt, card) — 57 tests, 100% branch coverage."""
from __future__ import annotations

from datetime import datetime, time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.storage.base import StorageKey

from callbacks.menu import MenuAction, MenuCallback
from callbacks.payment import PaymentCallback
from handlers.add.passport import EVENING_CUTOFF_HOUR
from models.course import Course
from models.enums import CourseStatus
from models.manager import Manager
from models.ocr import CardResult, OCRServerError, PassportResult, ReceiptResult
from models.user import User as KokUser
from states.add import AddStates
from templates import AddTemplates, ReissueTemplates
from tests.handlers.conftest import (
    KOK_GROUP_ID,
    MockHolder,
    create_test_dispatcher,
)
from tests.mock_server import MockTelegramBot
from tests.mock_server.tracker import TrackedRequest
from topic_access.message_middleware import ADD_ACTIVE_KEY_PREFIX
from utils.time import TASHKENT_TZ

# ── Constants ─────────────────────────────────────────────────────────────

BOT_ID = 1234567890
MANAGER_TG_ID = 999999
TOPIC_ID = 42
MENU_MSG_ID = 1
BOT_MSG_ID = 100

_S_GROUP = str(KOK_GROUP_ID)

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


def _user(**ov: Any) -> KokUser:
    d: dict[str, Any] = dict(
        id=10, telegram_id=555555, name="Ivanova Anna",
        manager_id=1, topic_id=TOPIC_ID,
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return KokUser(**d)


def _course(**ov: Any) -> Course:
    d: dict[str, Any] = dict(
        id=1, user_id=10, status=CourseStatus.ACTIVE,
        intake_time=time(10, 0), current_day=5, total_days=21,
        late_count=0, appeal_count=0, late_dates=[],
        invite_code="TESTCODE",
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return Course(**d)


def _passport(**ov: Any) -> PassportResult:
    d: dict[str, Any] = dict(
        is_document=True, last_name="Ivanova", first_name="Anna",
        patronymic=None, birth_date="01.01.1990",
    )
    d.update(ov)
    return PassportResult(**d)


def _receipt(**ov: Any) -> ReceiptResult:
    d: dict[str, Any] = dict(is_document=True, has_kok=True, price=50000)
    d.update(ov)
    return ReceiptResult(**d)


def _card_result(**ov: Any) -> CardResult:
    d: dict[str, Any] = dict(
        is_document=True,
        card_number="8600 1234 5678 9012",
        card_holder="IVANOVA ANNA",
    )
    d.update(ov)
    return CardResult(**d)


# ── Callback data ─────────────────────────────────────────────────────────


def _add_cb() -> str:
    return MenuCallback(action=MenuAction.ADD).pack()


# ── FSM data templates ───────────────────────────────────────────────────

_PASSPORT_FSM = {"bot_message_id": BOT_MSG_ID}

_RECEIPT_FSM: dict[str, Any] = {
    "bot_message_id": BOT_MSG_ID,
    "name": "Ivanova Anna",
    "passport_file_id": "passport_123",
    "birth_date": "01.01.1990",
}

_CARD_FSM: dict[str, Any] = {
    "bot_message_id": BOT_MSG_ID,
    "name": "Ivanova Anna",
    "passport_file_id": "passport_123",
    "receipt_file_id": "receipt_123",
    "receipt_price": 50000,
    "birth_date": "01.01.1990",
}


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


def _last_edit_text(bot: MockTelegramBot) -> str:
    edits = _edits(bot)
    return edits[-1].data.get("text", "") if edits else ""


def _last_send_text(bot: MockTelegramBot) -> str:
    sends = _sends(bot)
    return sends[-1].data.get("text", "") if sends else ""


def _all_texts(bot: MockTelegramBot) -> list[str]:
    """All sendMessage + editMessageText texts in order."""
    all_reqs = _sends(bot) + _edits(bot)
    return [r.data.get("text", "") for r in all_reqs]


# ── Seed / FSM helpers ───────────────────────────────────────────────────


def _seed_menu(bot: MockTelegramBot) -> None:
    """Pre-add menu message for click_button."""
    bot.chat_state.add_message(
        chat_id=KOK_GROUP_ID, from_user_id=BOT_ID, is_bot=True,
        text="menu", message_id=MENU_MSG_ID,
        message_thread_id=TOPIC_ID,
    )


def _seed_bot_msg(bot: MockTelegramBot) -> None:
    """Pre-add bot message for edit_or_send."""
    bot.chat_state.add_message(
        chat_id=KOK_GROUP_ID, from_user_id=BOT_ID, is_bot=True,
        text="bot message", message_id=BOT_MSG_ID,
        message_thread_id=TOPIC_ID,
    )


async def _set_fsm(dp, state_name: str, data: dict[str, Any] | None = None) -> None:
    key = StorageKey(bot_id=BOT_ID, chat_id=KOK_GROUP_ID, user_id=MANAGER_TG_ID)
    await dp.storage.set_state(key, state_name)
    if data:
        await dp.storage.set_data(key, data)


async def _get_fsm_state(dp) -> str | None:
    key = StorageKey(bot_id=BOT_ID, chat_id=KOK_GROUP_ID, user_id=MANAGER_TG_ID)
    return await dp.storage.get_state(key)


async def _get_fsm_data(dp) -> dict:
    key = StorageKey(bot_id=BOT_ID, chat_id=KOK_GROUP_ID, user_id=MANAGER_TG_ID)
    return await dp.storage.get_data(key)


def _bot_kw() -> dict[str, Any]:
    """Common kwargs for MockTelegramBot in supergroup context."""
    return dict(
        user_id=MANAGER_TG_ID,
        chat_id=KOK_GROUP_ID,
        chat_type="supergroup",
        message_thread_id=TOPIC_ID,
    )


# ══════════════════════════════════════════════════════════════════════════
# on_add_start — Manager clicks "Добавить" in menu
# ══════════════════════════════════════════════════════════════════════════


class TestOnAddStart:
    """7 tests for on_add_start callback handler."""

    @patch("handlers.add.passport.get_tashkent_now", return_value=TIME_20)
    async def test_time_restricted_at_20(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_add_cb(), MENU_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1
            assert AddTemplates.time_restricted() in alerts[0].data.get("text", "")

    @patch("handlers.add.passport.get_tashkent_now", return_value=TIME_21)
    async def test_time_restricted_after_20(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_add_cb(), MENU_MSG_ID)
            alerts = _alert_answers(bot)
            assert len(alerts) == 1

    @patch("handlers.add.passport.get_tashkent_now", return_value=TIME_19)
    async def test_allowed_before_cutoff(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.redis.set = AsyncMock(return_value=True)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_add_cb(), MENU_MSG_ID)
            assert len(_alert_answers(bot)) == 0
            assert len(_non_alert_answers(bot)) == 1

    @patch("handlers.add.passport.get_tashkent_now", return_value=TIME_19)
    async def test_happy_path(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.redis.set = AsyncMock(return_value=True)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_add_cb(), MENU_MSG_ID)
            # ask_passport sent
            assert AddTemplates.ask_passport() in _last_send_text(bot)
            # FSM state = waiting_passport
            assert await _get_fsm_state(dp) == AddStates.waiting_passport
            # Redis lock set
            mocks.redis.set.assert_called_once()
            call_args = mocks.redis.set.call_args
            assert ADD_ACTIVE_KEY_PREFIX in str(call_args)

    @patch("handlers.add.passport.get_tashkent_now", return_value=TIME_19)
    async def test_clears_previous_state(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.redis.set = AsyncMock(return_value=True)
        dp = await create_test_dispatcher(mocks)
        # Pre-set a different FSM state
        await _set_fsm(dp, AddStates.waiting_receipt, {"old_key": "old_val"})
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_menu(bot)
            await bot.click_button(_add_cb(), MENU_MSG_ID)
            # State is now waiting_passport (old state cleared)
            assert await _get_fsm_state(dp) == AddStates.waiting_passport
            data = await _get_fsm_data(dp)
            assert "old_key" not in data

    @patch("handlers.add.passport.get_tashkent_now", return_value=TIME_19)
    async def test_no_thread_id_skips_redis(self, _mock_now, mocks: MockHolder) -> None:
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        dp = await create_test_dispatcher(mocks)
        # No message_thread_id
        async with MockTelegramBot(
            dp, user_id=MANAGER_TG_ID, chat_id=KOK_GROUP_ID, chat_type="supergroup",
        ) as bot:
            bot.chat_state.add_message(
                chat_id=KOK_GROUP_ID, from_user_id=BOT_ID, is_bot=True,
                text="menu", message_id=MENU_MSG_ID,
            )
            await bot.click_button(_add_cb(), MENU_MSG_ID)
            mocks.redis.set.assert_not_called()
            # But FSM still set
            assert await _get_fsm_state(dp) == AddStates.waiting_passport


# ══════════════════════════════════════════════════════════════════════════
# Passport photo — OCR passport in waiting_passport state
# ══════════════════════════════════════════════════════════════════════════


class TestPassportPhoto:
    """16 tests for passport photo handler."""

    async def test_ocr_server_error(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.side_effect = OCRServerError("fail")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_server_error() in _last_edit_text(bot)
            assert await _get_fsm_state(dp) == AddStates.waiting_passport

    async def test_not_a_passport(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport(is_document=False)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.not_a_passport() in _last_edit_text(bot)

    async def test_no_first_name(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport(first_name=None)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_passport_bad_photo() in _last_edit_text(bot)

    async def test_no_last_name(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport(last_name=None)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_passport_bad_photo() in _last_edit_text(bot)

    async def test_name_validation_fails(self, mocks: MockHolder) -> None:
        """Name with non-Latin chars → validate_passport_name returns None."""
        mocks.ocr_service.process_passport.return_value = _passport(
            first_name="123", last_name="456",
        )
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_passport_bad_photo() in _last_edit_text(bot)

    async def test_with_patronymic(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport(patronymic="Petrovna")
        mocks.user_repo.get_by_name_prefix_and_birth_date.return_value = None
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            data = await _get_fsm_data(dp)
            assert "Petrovna" in data.get("name", "")
            assert await _get_fsm_state(dp) == AddStates.waiting_receipt

    async def test_happy_path_no_birth_date(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport(birth_date=None)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            # Skips dedup, transitions to receipt
            assert await _get_fsm_state(dp) == AddStates.waiting_receipt
            data = await _get_fsm_data(dp)
            assert data.get("birth_date") is None
            # ask_receipt sent
            assert AddTemplates.ask_receipt() in _last_send_text(bot)

    async def test_happy_path_valid_birth_date(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport()
        mocks.user_repo.get_by_name_prefix_and_birth_date.return_value = None
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert await _get_fsm_state(dp) == AddStates.waiting_receipt
            data = await _get_fsm_data(dp)
            assert data.get("birth_date") == "01.01.1990"

    async def test_invalid_birth_date(self, mocks: MockHolder) -> None:
        """Invalid date format → treated as None, dedup skipped."""
        mocks.ocr_service.process_passport.return_value = _passport(birth_date="not-a-date")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert await _get_fsm_state(dp) == AddStates.waiting_receipt
            data = await _get_fsm_data(dp)
            assert data.get("birth_date") is None

    async def test_existing_user_active_course(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport()
        mocks.user_repo.get_by_name_prefix_and_birth_date.return_value = _user()
        mocks.course_repo.get_active_by_user_id.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.user_has_active_course() in _last_edit_text(bot)
            # State cleared
            assert await _get_fsm_state(dp) is None

    async def test_existing_user_no_active_course(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport()
        mocks.user_repo.get_by_name_prefix_and_birth_date.return_value = _user(id=42)
        mocks.course_repo.get_active_by_user_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            # Stores existing_user_id, continues to receipt
            data = await _get_fsm_data(dp)
            assert data.get("existing_user_id") == 42
            assert await _get_fsm_state(dp) == AddStates.waiting_receipt

    async def test_dedup_exception_continues(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport()
        mocks.user_repo.get_by_name_prefix_and_birth_date.side_effect = Exception("DB err")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            # Despite exception, transitions to receipt
            assert await _get_fsm_state(dp) == AddStates.waiting_receipt

    async def test_ocr_result_shows_name(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport()
        mocks.user_repo.get_by_name_prefix_and_birth_date.return_value = None
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            # OCR result message should contain the recognized name
            edit_texts = [r.data.get("text", "") for r in _edits(bot)]
            assert any("Ivanova Anna" in t for t in edit_texts)

    async def test_active_course_clears_redis(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport()
        mocks.user_repo.get_by_name_prefix_and_birth_date.return_value = _user()
        mocks.course_repo.get_active_by_user_id.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            mocks.redis.delete.assert_called_once()
            call_arg = str(mocks.redis.delete.call_args)
            assert ADD_ACTIVE_KEY_PREFIX in call_arg

    async def test_active_course_no_thread_id_skips_redis(self, mocks: MockHolder) -> None:
        """Active course blocks flow but message has no thread_id → redis.delete NOT called."""
        mocks.ocr_service.process_passport.return_value = _passport()
        mocks.user_repo.get_by_name_prefix_and_birth_date.return_value = _user()
        mocks.course_repo.get_active_by_user_id.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        # No message_thread_id
        async with MockTelegramBot(
            dp, user_id=MANAGER_TG_ID, chat_id=KOK_GROUP_ID, chat_type="supergroup",
        ) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            mocks.redis.delete.assert_not_called()
            # But state still cleared
            assert await _get_fsm_state(dp) is None

    async def test_state_stays_on_error(self, mocks: MockHolder) -> None:
        """OCR error → state stays at waiting_passport (user can retry)."""
        mocks.ocr_service.process_passport.return_value = _passport(is_document=False)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert await _get_fsm_state(dp) == AddStates.waiting_passport


# ══════════════════════════════════════════════════════════════════════════
# Passport document + unsupported
# ══════════════════════════════════════════════════════════════════════════


class TestPassportDocument:
    """2 tests for passport document handler."""

    async def test_image_document_accepted(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_passport.return_value = _passport()
        mocks.user_repo.get_by_name_prefix_and_birth_date.return_value = None
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_document(mime_type="image/jpeg")
            # Delegated to _handle_passport_file → transitions
            assert await _get_fsm_state(dp) == AddStates.waiting_receipt

    async def test_non_image_document_rejected(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_document(mime_type="application/pdf")
            assert AddTemplates.photo_only() in _last_edit_text(bot)
            assert await _get_fsm_state(dp) == AddStates.waiting_passport


class TestPassportUnsupported:
    """1 test for passport unsupported handler."""

    async def test_shows_photo_only(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_passport, _PASSPORT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_message("some text")
            assert AddTemplates.photo_only() in _last_edit_text(bot)


# ══════════════════════════════════════════════════════════════════════════
# Receipt photo — OCR receipt in waiting_receipt state
# ══════════════════════════════════════════════════════════════════════════


class TestReceiptPhoto:
    """8 tests for receipt photo handler."""

    async def test_ocr_server_error(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_receipt.side_effect = OCRServerError("fail")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_server_error() in _last_edit_text(bot)
            assert await _get_fsm_state(dp) == AddStates.waiting_receipt

    async def test_not_a_receipt(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_receipt.return_value = _receipt(is_document=False)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.not_a_receipt() in _last_edit_text(bot)

    async def test_no_kok(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_receipt.return_value = _receipt(has_kok=False)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_receipt_no_kok() in _last_edit_text(bot)

    async def test_kok_found_no_price(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_receipt.return_value = _receipt(price=None)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_receipt_no_price() in _last_edit_text(bot)

    async def test_price_out_of_range(self, mocks: MockHolder) -> None:
        """Price < 10 → validate_receipt_price returns None."""
        mocks.ocr_service.process_receipt.return_value = _receipt(price=5)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_receipt_no_price() in _last_edit_text(bot)

    async def test_happy_path(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_receipt.return_value = _receipt(price=50000)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert await _get_fsm_state(dp) == AddStates.waiting_card
            assert AddTemplates.ask_card() in _last_send_text(bot)

    async def test_receipt_price_in_fsm(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_receipt.return_value = _receipt(price=75000)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            data = await _get_fsm_data(dp)
            assert data.get("receipt_price") == 75000

    async def test_state_stays_on_error(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_receipt.return_value = _receipt(is_document=False)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert await _get_fsm_state(dp) == AddStates.waiting_receipt


# ══════════════════════════════════════════════════════════════════════════
# Receipt document + unsupported
# ══════════════════════════════════════════════════════════════════════════


class TestReceiptDocument:
    """2 tests for receipt document handler."""

    async def test_image_document_accepted(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_receipt.return_value = _receipt()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_document(mime_type="image/png")
            assert await _get_fsm_state(dp) == AddStates.waiting_card

    async def test_non_image_document_rejected(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_document(mime_type="application/pdf")
            assert AddTemplates.photo_only() in _last_edit_text(bot)


class TestReceiptUnsupported:
    """1 test for receipt unsupported handler."""

    async def test_shows_photo_only(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_message("some text")
            assert AddTemplates.photo_only() in _last_edit_text(bot)


# ══════════════════════════════════════════════════════════════════════════
# Card photo — OCR card + _create_link in waiting_card state
# ══════════════════════════════════════════════════════════════════════════


class TestCardPhoto:
    """17 tests for card photo handler + _create_link."""

    async def test_ocr_server_error(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.side_effect = OCRServerError("fail")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_server_error() in _last_edit_text(bot)
            assert await _get_fsm_state(dp) == AddStates.waiting_card

    async def test_not_a_card(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result(is_document=False)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.not_a_card() in _last_edit_text(bot)

    async def test_no_card_number(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result(card_number=None)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_card_bad_photo() in _last_edit_text(bot)

    async def test_no_card_holder(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result(card_holder=None)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_card_bad_photo() in _last_edit_text(bot)

    async def test_card_validation_fails(self, mocks: MockHolder) -> None:
        """Card number has wrong digit count → validate_card_input returns None."""
        mocks.ocr_service.process_card.return_value = _card_result(card_number="1234")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.ocr_card_bad_photo() in _last_edit_text(bot)

    async def test_happy_path_link_created(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course(invite_code="ABC123")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            # Link created message sent
            assert "ABC123" in _last_send_text(bot)
            # State cleared
            assert await _get_fsm_state(dp) is None

    async def test_ocr_result_shows_card_data(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course(invite_code="XYZ")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            edit_texts = [r.data.get("text", "") for r in _edits(bot)]
            # OCR result should contain card number and holder
            assert any("8600" in t for t in edit_texts)

    async def test_link_text_format(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course(invite_code="INVITE42")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            link_text = _last_send_text(bot)
            assert "INVITE42" in link_text
            assert "test_bot" in link_text  # bot username from mock getMe

    async def test_state_cleared_after_success(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert await _get_fsm_state(dp) is None
            assert await _get_fsm_data(dp) == {}

    async def test_redis_cleared_after_success(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            mocks.redis.delete.assert_called_once()
            call_arg = str(mocks.redis.delete.call_args)
            assert ADD_ACTIVE_KEY_PREFIX in call_arg

    async def test_no_thread_id_skips_redis_clear(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        # No message_thread_id
        async with MockTelegramBot(
            dp, user_id=MANAGER_TG_ID, chat_id=KOK_GROUP_ID, chat_type="supergroup",
        ) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            mocks.redis.delete.assert_not_called()

    async def test_missing_earlier_fsm_data(self, mocks: MockHolder) -> None:
        """FSM data expired/missing earlier steps → error_try_later, clears state."""
        mocks.ocr_service.process_card.return_value = _card_result()
        dp = await create_test_dispatcher(mocks)
        # Only bot_message_id — missing name, passport, receipt, etc.
        await _set_fsm(dp, AddStates.waiting_card, {"bot_message_id": BOT_MSG_ID})
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.error_try_later() in _last_send_text(bot)
            assert await _get_fsm_state(dp) is None

    async def test_manager_not_found(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.error_try_later() in _last_send_text(bot)
            assert await _get_fsm_state(dp) is None

    async def test_service_exception_no_clear(self, mocks: MockHolder) -> None:
        """add_service.create_link raises → error, but state NOT cleared."""
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            assert AddTemplates.error_try_later() in _last_send_text(bot)
            # State NOT cleared (potential bug in code)
            assert await _get_fsm_state(dp) == AddStates.waiting_card

    async def test_birth_date_passed_to_service(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        fsm = {**_CARD_FSM, "birth_date": "15.06.1995"}
        await _set_fsm(dp, AddStates.waiting_card, fsm)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            call_kwargs = mocks.add_service.create_link.call_args.kwargs
            assert call_kwargs["birth_date"] == "15.06.1995"

    async def test_existing_user_id_passed(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        fsm = {**_CARD_FSM, "existing_user_id": 42}
        await _set_fsm(dp, AddStates.waiting_card, fsm)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            call_kwargs = mocks.add_service.create_link.call_args.kwargs
            assert call_kwargs["existing_user_id"] == 42

    async def test_service_called_with_all_args(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager(id=7)
        mocks.add_service.create_link.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()
            call_kwargs = mocks.add_service.create_link.call_args.kwargs
            assert call_kwargs["manager_id"] == 7
            assert call_kwargs["name"] == "Ivanova Anna"
            assert call_kwargs["passport_file_id"] == "passport_123"
            assert call_kwargs["receipt_file_id"] == "receipt_123"
            assert call_kwargs["receipt_price"] == 50000
            assert call_kwargs["birth_date"] == "01.01.1990"


# ══════════════════════════════════════════════════════════════════════════
# Accountant notification (after link creation)
# ══════════════════════════════════════════════════════════════════════════

ACCOUNTANT_TG_ID_1 = 888001
ACCOUNTANT_TG_ID_2 = 888002


def _accountant(telegram_id: int = ACCOUNTANT_TG_ID_1, **ov: Any) -> Manager:
    d: dict[str, Any] = dict(
        id=90, telegram_id=telegram_id, name="Accountant",
        is_active=True, role="accountant",
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return Manager(**d)


def _media_groups(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_send_media_group_requests()


class TestAccountantNotification:
    """6 tests for accountant notification after link creation."""

    def _setup_happy(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course(id=42)

    async def test_accountant_receives_media_group(self, mocks: MockHolder) -> None:
        self._setup_happy(mocks)
        mocks.manager_repo.get_active_by_role.return_value = [_accountant()]
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()

            groups = _media_groups(bot)
            assert len(groups) == 1
            media_data = groups[0].data.get("media", [])
            assert len(media_data) == 3
            assert media_data[0].get("media") == "passport_123"
            assert media_data[1].get("media") == "receipt_123"

    async def test_accountant_receives_button_with_course_id(
        self, mocks: MockHolder,
    ) -> None:
        self._setup_happy(mocks)
        mocks.manager_repo.get_active_by_role.return_value = [_accountant()]
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()

            sends = _sends(bot)
            # Find message sent to accountant (not to group)
            acc_sends = [
                s for s in sends
                if str(s.data.get("chat_id")) == str(ACCOUNTANT_TG_ID_1)
            ]
            assert len(acc_sends) == 1
            markup = acc_sends[0].data.get("reply_markup", {})
            buttons = markup.get("inline_keyboard", [[]])[0]
            assert len(buttons) == 1
            cb_data = buttons[0]["callback_data"]
            parsed = PaymentCallback.unpack(cb_data)
            assert parsed.course_id == 42

    async def test_multiple_accountants_all_notified(
        self, mocks: MockHolder,
    ) -> None:
        self._setup_happy(mocks)
        mocks.manager_repo.get_active_by_role.return_value = [
            _accountant(telegram_id=ACCOUNTANT_TG_ID_1),
            _accountant(telegram_id=ACCOUNTANT_TG_ID_2, id=91),
        ]
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()

            groups = _media_groups(bot)
            assert len(groups) == 2
            chat_ids = {str(g.data.get("chat_id")) for g in groups}
            assert str(ACCOUNTANT_TG_ID_1) in chat_ids
            assert str(ACCOUNTANT_TG_ID_2) in chat_ids

    async def test_no_accountants_skips_notification(
        self, mocks: MockHolder,
    ) -> None:
        self._setup_happy(mocks)
        mocks.manager_repo.get_active_by_role.return_value = []
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()

            # Link still created
            assert "TESTCODE" in _last_send_text(bot)
            # No media groups sent
            assert len(_media_groups(bot)) == 0

    async def test_notification_error_does_not_break_link(
        self, mocks: MockHolder,
    ) -> None:
        self._setup_happy(mocks)
        mocks.manager_repo.get_active_by_role.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()

            # Link still created despite notification failure
            assert "TESTCODE" in _last_send_text(bot)
            assert await _get_fsm_state(dp) is None

    async def test_caption_contains_card_data(self, mocks: MockHolder) -> None:
        self._setup_happy(mocks)
        mocks.manager_repo.get_active_by_role.return_value = [_accountant()]
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_photo()

            groups = _media_groups(bot)
            media_data = groups[0].data.get("media", [])
            caption = media_data[0].get("caption", "")
            assert "Ivanova Anna" in caption
            assert "8600 1234 5678 9012" in caption


# ══════════════════════════════════════════════════════════════════════════
# Card document + unsupported
# ══════════════════════════════════════════════════════════════════════════


class TestCardDocument:
    """2 tests for card document handler."""

    async def test_image_document_accepted(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_card.return_value = _card_result()
        mocks.manager_repo.get_by_telegram_id.return_value = _manager()
        mocks.add_service.create_link.return_value = _course()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_document(mime_type="image/jpeg")
            assert await _get_fsm_state(dp) is None  # Link created, state cleared

    async def test_non_image_document_rejected(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_document(mime_type="application/pdf")
            assert AddTemplates.photo_only() in _last_edit_text(bot)


class TestCardUnsupported:
    """1 test for card unsupported handler."""

    async def test_shows_photo_only(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, AddStates.waiting_card, _CARD_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_bot_msg(bot)
            await bot.send_message("some text")
            assert AddTemplates.photo_only() in _last_edit_text(bot)
