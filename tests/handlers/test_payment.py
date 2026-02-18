"""Tests for handlers/payment.py — receipt upload by accountant."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.storage.base import StorageKey

from callbacks.payment import PaymentCallback
from models.course import Course
from models.enums import CourseStatus
from models.manager import Manager
from models.ocr import OCRServerError, PaymentReceiptResult
from models.payment_receipt import PaymentReceipt
from models.user import User as KokUser
from states.payment import PaymentStates
from templates import PaymentTemplates
from tests.handlers.conftest import MockHolder, create_test_dispatcher
from tests.mock_server import MockTelegramBot
from tests.mock_server.tracker import TrackedRequest

# ── Constants ─────────────────────────────────────────────────────────────

BOT_ID = 1234567890
ACCOUNTANT_TG_ID = 888001
COURSE_ID = 42
MANAGER_ID = 1
MANAGER_TG_ID = 999999
BOT_MSG_ID = 100
BUTTON_MSG_ID = 200


# ── Factories ─────────────────────────────────────────────────────────────


def _course(**ov: Any) -> Course:
    d: dict[str, Any] = dict(
        id=COURSE_ID, user_id=10, status=CourseStatus.ACTIVE,
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return Course(**d)


def _user(**ov: Any) -> KokUser:
    d: dict[str, Any] = dict(
        id=10, telegram_id=555555, name="Ivanova Anna",
        manager_id=MANAGER_ID, topic_id=42,
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return KokUser(**d)


def _accountant(**ov: Any) -> Manager:
    d: dict[str, Any] = dict(
        id=90, telegram_id=ACCOUNTANT_TG_ID, name="Accountant",
        is_active=True, role="accountant",
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return Manager(**d)


def _manager(**ov: Any) -> Manager:
    d: dict[str, Any] = dict(
        id=MANAGER_ID, telegram_id=MANAGER_TG_ID, name="Test Manager",
        is_active=True, role="manager",
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return Manager(**d)


def _ocr_ok(**ov: Any) -> PaymentReceiptResult:
    d: dict[str, Any] = dict(is_document=True, amount=150_000)
    d.update(ov)
    return PaymentReceiptResult(**d)


def _receipt(**ov: Any) -> PaymentReceipt:
    d: dict[str, Any] = dict(
        id=1, course_id=COURSE_ID, accountant_id=90,
        receipt_file_id="old_receipt", amount=100_000,
        created_at=datetime(2025, 1, 1),
    )
    d.update(ov)
    return PaymentReceipt(**d)


# ── Helpers ───────────────────────────────────────────────────────────────


def _send_cb() -> str:
    return PaymentCallback(action="send", course_id=COURSE_ID).pack()


def _cancel_cb() -> str:
    return PaymentCallback(action="cancel", course_id=COURSE_ID).pack()


def _bot_kw() -> dict[str, Any]:
    return dict(user_id=ACCOUNTANT_TG_ID, chat_id=ACCOUNTANT_TG_ID, chat_type="private")


async def _set_fsm(dp, state_name: str, data: dict[str, Any] | None = None) -> None:
    key = StorageKey(bot_id=BOT_ID, chat_id=ACCOUNTANT_TG_ID, user_id=ACCOUNTANT_TG_ID)
    await dp.storage.set_state(key, state_name)
    if data:
        await dp.storage.set_data(key, data)


async def _get_fsm_state(dp) -> str | None:
    key = StorageKey(bot_id=BOT_ID, chat_id=ACCOUNTANT_TG_ID, user_id=ACCOUNTANT_TG_ID)
    return await dp.storage.get_state(key)


def _sends(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_send_message_requests()


def _edits(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_requests_by_method("editMessageText")


def _edit_markups(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_edit_message_reply_markup_requests()


def _photos(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_send_photo_requests()


def _answers(bot: MockTelegramBot) -> list[TrackedRequest]:
    return bot._server.tracker.get_answer_callback_query_requests()


def _seed_button_msg(bot: MockTelegramBot) -> None:
    """Seed a bot message with the "📎 Отправить чек" button."""
    bot.chat_state.add_message(
        chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
        text="Загрузите чек об оплате", message_id=BUTTON_MSG_ID,
    )


_RECEIPT_FSM: dict[str, Any] = {
    "bot_message_id": BOT_MSG_ID,
    "course_id": COURSE_ID,
    "button_message_id": BUTTON_MSG_ID,
    "manager_id": MANAGER_ID,
    "girl_name": "Ivanova Anna",
}


# ══════════════════════════════════════════════════════════════════════════
# Callback: "📎 Отправить чек"
# ══════════════════════════════════════════════════════════════════════════


class TestSendReceiptCallback:
    """Tests for clicking the send receipt button."""

    async def test_button_changes_to_cancel(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = _course()
        mocks.user_repo.get_by_id.return_value = _user()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_button_msg(bot)
            await bot.click_button(_send_cb(), message_id=BUTTON_MSG_ID)

            markups = _edit_markups(bot)
            assert len(markups) >= 1
            markup = markups[0].data.get("reply_markup", {})
            buttons = markup.get("inline_keyboard", [[]])[0]
            assert "Отменить" in buttons[0].get("text", "")

    async def test_prompt_sent_with_girl_name(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = _course()
        mocks.user_repo.get_by_id.return_value = _user(name="Petrova Maria")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_button_msg(bot)
            await bot.click_button(_send_cb(), message_id=BUTTON_MSG_ID)

            sends = _sends(bot)
            texts = [s.data.get("text", "") for s in sends]
            assert any("Petrova Maria" in t for t in texts)

    async def test_fsm_set_to_waiting_receipt(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = _course()
        mocks.user_repo.get_by_id.return_value = _user()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_button_msg(bot)
            await bot.click_button(_send_cb(), message_id=BUTTON_MSG_ID)

            state = await _get_fsm_state(dp)
            assert state == PaymentStates.waiting_receipt.state

    async def test_course_not_found_shows_alert(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_button_msg(bot)
            await bot.click_button(_send_cb(), message_id=BUTTON_MSG_ID)

            answers = _answers(bot)
            assert len(answers) >= 1
            assert str(answers[0].data.get("show_alert")).lower() == "true"
            assert "не найден" in answers[0].data.get("text", "")

    async def test_completed_course_shows_alert(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = _course(status=CourseStatus.COMPLETED)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_button_msg(bot)
            await bot.click_button(_send_cb(), message_id=BUTTON_MSG_ID)

            answers = _answers(bot)
            assert len(answers) >= 1
            assert str(answers[0].data.get("show_alert")).lower() == "true"
            assert "завершён" in answers[0].data.get("text", "").lower()

    async def test_refused_course_shows_alert(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = _course(status=CourseStatus.REFUSED)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_button_msg(bot)
            await bot.click_button(_send_cb(), message_id=BUTTON_MSG_ID)

            answers = _answers(bot)
            assert len(answers) >= 1
            assert str(answers[0].data.get("show_alert")).lower() == "true"

    async def test_user_not_found_logs_error(self, mocks: MockHolder) -> None:
        mocks.course_repo.get_by_id.return_value = _course()
        mocks.user_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_button_msg(bot)
            with patch("handlers.payment.logger") as mock_logger:
                await bot.click_button(_send_cb(), message_id=BUTTON_MSG_ID)
                mock_logger.error.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# Callback: "❌ Отменить"
# ══════════════════════════════════════════════════════════════════════════


class TestCancelReceiptCallback:
    """Tests for clicking the cancel button."""

    async def test_cancel_reverts_button_and_clears_fsm(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            _seed_button_msg(bot)
            # Also seed the prompt message so it can be deleted
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото чека", message_id=BOT_MSG_ID,
            )
            await bot.click_button(_cancel_cb(), message_id=BUTTON_MSG_ID)

            markups = _edit_markups(bot)
            assert len(markups) >= 1
            markup = markups[0].data.get("reply_markup", {})
            buttons = markup.get("inline_keyboard", [[]])[0]
            assert "Отправить чек" in buttons[0].get("text", "")

            state = await _get_fsm_state(dp)
            assert state is None


# ══════════════════════════════════════════════════════════════════════════
# Photo receipt — happy path
# ══════════════════════════════════════════════════════════════════════════


class TestReceiptPhoto:
    """Tests for photo receipt processing."""

    def _setup_happy(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_payment_receipt.return_value = _ocr_ok()
        mocks.manager_repo.get_by_telegram_id.return_value = _accountant()
        mocks.payment_receipt_repo.get_by_course_id.return_value = None
        mocks.manager_repo.get_by_id.return_value = _manager()

    async def test_receipt_accepted_and_saved(self, mocks: MockHolder) -> None:
        self._setup_happy(mocks)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото", message_id=BOT_MSG_ID,
            )
            await bot.send_photo(file_id="receipt_photo_123")

            mocks.payment_receipt_repo.create.assert_called_once_with(
                course_id=COURSE_ID,
                accountant_id=90,
                receipt_file_id="receipt_photo_123",
                amount=150_000,
            )

            state = await _get_fsm_state(dp)
            assert state is None

    async def test_receipt_accepted_message(self, mocks: MockHolder) -> None:
        self._setup_happy(mocks)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото", message_id=BOT_MSG_ID,
            )
            await bot.send_photo()

            edits = _edits(bot)
            texts = [e.data.get("text", "") for e in edits]
            assert any("Чек принят" in t for t in texts)
            assert any("150 000" in t for t in texts)

    async def test_receipt_forwarded_to_manager(self, mocks: MockHolder) -> None:
        self._setup_happy(mocks)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото", message_id=BOT_MSG_ID,
            )
            await bot.send_photo(file_id="receipt_photo_123")

            photos = _photos(bot)
            manager_photos = [
                p for p in photos
                if str(p.data.get("chat_id")) == str(MANAGER_TG_ID)
            ]
            assert len(manager_photos) == 1
            assert "Ivanova Anna" in manager_photos[0].data.get("caption", "")

    async def test_button_message_updated_after_accept(self, mocks: MockHolder) -> None:
        self._setup_happy(mocks)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Загрузите чек", message_id=BOT_MSG_ID,
            )
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Загрузите чек об оплате", message_id=BUTTON_MSG_ID,
            )
            await bot.send_photo()

            edits = _edits(bot)
            button_edits = [
                e for e in edits
                if str(e.data.get("message_id")) == str(BUTTON_MSG_ID)
            ]
            assert len(button_edits) >= 1
            assert "Чек загружен" in button_edits[0].data.get("text", "")


# ══════════════════════════════════════════════════════════════════════════
# Photo receipt — duplicate / forward failure
# ══════════════════════════════════════════════════════════════════════════


class TestReceiptDuplicateAndForward:
    """Tests for duplicate receipt and forward failure."""

    async def test_duplicate_receipt_shows_already_uploaded(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_payment_receipt.return_value = _ocr_ok()
        mocks.manager_repo.get_by_telegram_id.return_value = _accountant()
        mocks.payment_receipt_repo.get_by_course_id.return_value = _receipt()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото", message_id=BOT_MSG_ID,
            )
            await bot.send_photo(file_id="receipt_photo_dup")

            mocks.payment_receipt_repo.create.assert_not_called()

            edits = _edits(bot)
            texts = [e.data.get("text", "") for e in edits]
            assert any("уже загружен" in t.lower() for t in texts)

            state = await _get_fsm_state(dp)
            assert state is None

    async def test_forward_failure_still_saves_receipt(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_payment_receipt.return_value = _ocr_ok()
        mocks.manager_repo.get_by_telegram_id.return_value = _accountant()
        mocks.payment_receipt_repo.get_by_course_id.return_value = None
        mocks.manager_repo.get_by_id.return_value = _manager()
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото", message_id=BOT_MSG_ID,
            )
            # Make _forward_to_manager fail by making get_by_id raise
            mocks.manager_repo.get_by_id.side_effect = RuntimeError("DB down")

            with patch("handlers.payment.logger") as mock_logger:
                await bot.send_photo(file_id="receipt_photo_fwd_fail")

                mocks.payment_receipt_repo.create.assert_called_once()
                mock_logger.warning.assert_called_once()

            state = await _get_fsm_state(dp)
            assert state is None


# ══════════════════════════════════════════════════════════════════════════
# Photo receipt — OCR errors
# ══════════════════════════════════════════════════════════════════════════


class TestReceiptOCRErrors:
    """Tests for OCR error handling."""

    async def test_not_a_receipt(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_payment_receipt.return_value = _ocr_ok(is_document=False)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото", message_id=BOT_MSG_ID,
            )
            await bot.send_photo()

            edits = _edits(bot)
            texts = [e.data.get("text", "") for e in edits]
            assert any("не чек" in t.lower() for t in texts)

            state = await _get_fsm_state(dp)
            assert state == PaymentStates.waiting_receipt.state

    async def test_no_amount(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_payment_receipt.return_value = _ocr_ok(amount=None)
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото", message_id=BOT_MSG_ID,
            )
            await bot.send_photo()

            edits = _edits(bot)
            texts = [e.data.get("text", "") for e in edits]
            assert any("сумму" in t.lower() for t in texts)

            state = await _get_fsm_state(dp)
            assert state == PaymentStates.waiting_receipt.state

    async def test_server_error(self, mocks: MockHolder) -> None:
        mocks.ocr_service.process_payment_receipt.side_effect = OCRServerError("fail")
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото", message_id=BOT_MSG_ID,
            )
            await bot.send_photo()

            edits = _edits(bot)
            texts = [e.data.get("text", "") for e in edits]
            assert any("сервера" in t.lower() for t in texts)

            state = await _get_fsm_state(dp)
            assert state == PaymentStates.waiting_receipt.state


# ══════════════════════════════════════════════════════════════════════════
# Unsupported message
# ══════════════════════════════════════════════════════════════════════════


class TestReceiptUnsupported:
    """Test unsupported message types in waiting_receipt state."""

    async def test_text_message_shows_photo_only(self, mocks: MockHolder) -> None:
        dp = await create_test_dispatcher(mocks)
        await _set_fsm(dp, PaymentStates.waiting_receipt, _RECEIPT_FSM)
        async with MockTelegramBot(dp, **_bot_kw()) as bot:
            bot.chat_state.add_message(
                chat_id=ACCOUNTANT_TG_ID, from_user_id=BOT_ID, is_bot=True,
                text="Отправьте фото", message_id=BOT_MSG_ID,
            )
            await bot.send_message("some text")

            edits = _edits(bot)
            texts = [e.data.get("text", "") for e in edits]
            assert any("фото чека" in t.lower() for t in texts)

            state = await _get_fsm_state(dp)
            assert state == PaymentStates.waiting_receipt.state
