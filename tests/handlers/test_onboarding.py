"""Tests for handlers/onboarding.py — 78 tests, 100% branch coverage."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Chat, Message, MessageEntity, Update, User

from callbacks.onboarding import OnboardingAction, OnboardingCallback
from models.course import Course
from models.enums import CourseStatus
from models.manager import Manager
from models.user import User as KokUser
from states.onboarding import OnboardingStates
from templates import OnboardingTemplates
from tests.handlers.conftest import (
    KOK_GROUP_ID,
    MockHolder,
    create_test_dispatcher,
)
from tests.mock_server import MockTelegramBot
from utils.time import TASHKENT_TZ

# ── Constants ─────────────────────────────────────────────────────────────

BOT_ID = 1234567890
USER_ID = 123456789

FIXED_NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=TASHKENT_TZ)
TODAY = FIXED_NOW.date()
YESTERDAY = TODAY - timedelta(days=1)

# Pre-built callback data
CB_UNDERSTOOD = OnboardingCallback(action=OnboardingAction.UNDERSTOOD).pack()
CB_DAY_1 = OnboardingCallback(action=OnboardingAction.CYCLE_DAY, value="1").pack()
CB_DAY_4 = OnboardingCallback(action=OnboardingAction.CYCLE_DAY, value="4").pack()
CB_TIME_1430 = OnboardingCallback(action=OnboardingAction.TIME, value="14-30").pack()
CB_RULES_OK = OnboardingCallback(action=OnboardingAction.RULES_OK).pack()
CB_ACCEPT = OnboardingCallback(action=OnboardingAction.ACCEPT).pack()


# ── Factories ─────────────────────────────────────────────────────────────


def _make_course(**overrides) -> Course:
    defaults = dict(
        id=1,
        user_id=10,
        status=CourseStatus.SETUP,
        invite_code="TESTCODE",
        invite_used=False,
        created_at=datetime(2025, 1, 15, 8, 0, 0, tzinfo=TASHKENT_TZ),
    )
    defaults.update(overrides)
    return Course(**defaults)


def _make_user(**overrides) -> KokUser:
    defaults = dict(
        id=10,
        telegram_id=None,
        name="Иванова Мария Петровна",
        manager_id=5,
        topic_id=None,
        created_at=datetime(2025, 1, 15, 8, 0, 0, tzinfo=TASHKENT_TZ),
    )
    defaults.update(overrides)
    return KokUser(**defaults)


def _make_manager(**overrides) -> Manager:
    defaults = dict(
        id=5,
        telegram_id=999888777,
        name="Алина",
        is_active=True,
        role="manager",
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=TASHKENT_TZ),
    )
    defaults.update(overrides)
    return Manager(**defaults)


# ── Helpers ───────────────────────────────────────────────────────────────


async def _send_start(bot: MockTelegramBot, args: str = "") -> None:
    """Send /start command with proper bot_command entity."""
    text = f"/start {args}" if args else "/start"
    msg_id = bot._update_builder._get_next_message_id()
    upd_id = bot._update_builder._get_next_update_id()
    update = Update(
        update_id=upd_id,
        message=Message(
            message_id=msg_id,
            date=datetime.now(),
            chat=Chat(
                id=bot.chat_id, type="private",
                first_name="Test", last_name="User", username="testuser",
            ),
            from_user=User(
                id=bot.user_id, is_bot=False,
                first_name="Test", last_name="User",
                username="testuser", language_code="ru",
            ),
            text=text,
            entities=[MessageEntity(type="bot_command", offset=0, length=6)],
        ),
    )
    bot.chat_state.add_message(
        chat_id=bot.chat_id,
        from_user_id=bot.user_id,
        is_bot=False,
        text=text,
        message_id=msg_id,
    )
    await bot.dispatcher.feed_update(bot.bot, update)


def _inject_bot_message(
    bot: MockTelegramBot,
    text: str,
    reply_markup: dict | None = None,
) -> int:
    """Inject a bot message into chat_state. Returns message_id."""
    msg = bot.chat_state.add_message(
        chat_id=bot.chat_id,
        from_user_id=BOT_ID,
        is_bot=True,
        text=text,
        reply_markup=reply_markup,
    )
    return msg.message_id


async def _get_fsm_state(dp, user_id: int, chat_id: int) -> str | None:
    key = StorageKey(bot_id=BOT_ID, chat_id=chat_id, user_id=user_id)
    return await dp.storage.get_state(key)


async def _get_fsm_data(dp, user_id: int, chat_id: int) -> dict:
    key = StorageKey(bot_id=BOT_ID, chat_id=chat_id, user_id=user_id)
    return await dp.storage.get_data(key)


async def _set_fsm(dp, user_id: int, chat_id: int, state, data: dict) -> None:
    """Set FSM state and data."""
    key = StorageKey(bot_id=BOT_ID, chat_id=chat_id, user_id=user_id)
    await dp.storage.set_state(key, state)
    await dp.storage.set_data(key, data)


def _base_fsm_data(bot_message_id: int, **extra) -> dict:
    """Default FSM data for onboarding steps."""
    data = {
        "course_id": 1,
        "user_id": 10,
        "manager_id": 5,
        "user_name": "Иванова Мария Петровна",
        "bot_message_id": bot_message_id,
        "course_created_date": TODAY.isoformat(),
    }
    data.update(extra)
    return data


# ── Module-level fixtures ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_time():
    """Fix time to 2025-01-15 10:00 Tashkent for all tests."""
    with (
        patch("handlers.onboarding.get_tashkent_now", return_value=FIXED_NOW),
        patch("keyboards.onboarding.get_tashkent_now", return_value=FIXED_NOW),
    ):
        yield


# ── TestOnStart ───────────────────────────────────────────────────────────


class TestOnStart:
    """Tests for on_start handler (lines 51-151)."""

    async def test_no_invite_code(self, mocks: MockHolder):
        """Line 61: /start without args → 'Попроси ссылку'."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot)
            bot.assert_last_bot_message_contains(OnboardingTemplates.no_link())
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_empty_invite_code_spaces(self, mocks: MockHolder):
        """Line 59: /start with only spaces → same as no code."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "   ")
            bot.assert_last_bot_message_contains(OnboardingTemplates.no_link())

    async def test_manager_start_gets_greeting(self, mocks: MockHolder):
        """/start without invite → manager gets manager greeting."""
        mocks.manager_repo.get_by_telegram_id.return_value = _make_manager(
            role="manager",
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot)
            bot.assert_last_bot_message_contains("Привет")
            bot.assert_last_bot_message_contains("в группе")

    async def test_accountant_start_gets_greeting(self, mocks: MockHolder):
        """/start without invite → accountant gets accountant greeting."""
        mocks.manager_repo.get_by_telegram_id.return_value = _make_manager(
            role="accountant",
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot)
            bot.assert_last_bot_message_contains("Привет")
            bot.assert_last_bot_message_contains("оплаты")

    async def test_unknown_user_start_gets_no_link(self, mocks: MockHolder):
        """/start without invite → unknown user gets 'ask manager'."""
        mocks.manager_repo.get_by_telegram_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot)
            bot.assert_last_bot_message_contains(OnboardingTemplates.no_link())

    async def test_db_error_on_lookup(self, mocks: MockHolder):
        """Line 67: get_by_invite_code raises → 'Ссылка недействительна'."""
        mocks.course_repo.get_by_invite_code.side_effect = Exception("DB down")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "CODE")
            bot.assert_last_bot_message_contains(OnboardingTemplates.invalid_link())

    async def test_course_not_found(self, mocks: MockHolder):
        """Line 72: course is None → 'Ссылка недействительна'."""
        mocks.course_repo.get_by_invite_code.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "INVALID")
            bot.assert_last_bot_message_contains(OnboardingTemplates.invalid_link())

    async def test_invite_already_used(self, mocks: MockHolder):
        """Line 76: invite_used=True → 'Ссылка уже использована'."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course(invite_used=True)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            bot.assert_last_bot_message_contains(OnboardingTemplates.link_used())

    async def test_course_status_expired(self, mocks: MockHolder):
        """Line 80: status=EXPIRED → 'должна была зарегистрироваться DD.MM.YYYY'."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course(
            status=CourseStatus.EXPIRED,
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            bot.assert_last_bot_message_contains("должна была зарегистрироваться")
            bot.assert_last_bot_message_contains("15.01.2025")

    async def test_course_expired_by_date(self, mocks: MockHolder):
        """Line 86: created_at yesterday → _check_and_expire → expired + set_expired called."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course(
            created_at=datetime(2025, 1, 14, 8, 0, 0, tzinfo=TASHKENT_TZ),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            bot.assert_last_bot_message_contains("должна была зарегистрироваться")
            bot.assert_last_bot_message_contains("14.01.2025")
            mocks.course_repo.set_expired.assert_called_once_with(1)

    async def test_course_status_not_setup(self, mocks: MockHolder):
        """Line 92: status=ACTIVE (not SETUP) → 'Ссылка недействительна'."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course(
            status=CourseStatus.ACTIVE,
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            bot.assert_last_bot_message_contains(OnboardingTemplates.invalid_link())

    async def test_user_db_error(self, mocks: MockHolder):
        """Line 99: get_by_id raises → 'Ссылка недействительна'."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course()
        mocks.user_repo.get_by_id.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            bot.assert_last_bot_message_contains(OnboardingTemplates.invalid_link())

    async def test_user_not_found(self, mocks: MockHolder):
        """Line 104: user is None → 'Ссылка недействительна'."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course()
        mocks.user_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            bot.assert_last_bot_message_contains(OnboardingTemplates.invalid_link())

    async def test_another_user_claimed_link(self, mocks: MockHolder):
        """Line 110: user.telegram_id differs from sender → invalid."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course()
        mocks.user_repo.get_by_id.return_value = _make_user(telegram_id=999)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            bot.assert_last_bot_message_contains(OnboardingTemplates.invalid_link())

    async def test_sets_telegram_id_first_use(self, mocks: MockHolder):
        """Line 118: user.telegram_id is None → set_telegram_id called."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course()
        mocks.user_repo.get_by_id.return_value = _make_user(telegram_id=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            mocks.user_repo.set_telegram_id.assert_called_once_with(10, USER_ID)

    async def test_set_telegram_id_fails(self, mocks: MockHolder):
        """Line 119: set_telegram_id raises → invalid link."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course()
        mocks.user_repo.get_by_id.return_value = _make_user(telegram_id=None)
        mocks.user_repo.set_telegram_id.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            bot.assert_last_bot_message_contains(OnboardingTemplates.invalid_link())

    async def test_resend_same_course_in_progress(self, mocks: MockHolder):
        """Line 128: already in onboarding with same course → resend step."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course()
        mocks.user_repo.get_by_id.return_value = _make_user(telegram_id=USER_ID)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "old text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(msg_id),
            )
            await _send_start(bot, "TESTCODE")
            # Should resend instructions (edit existing message)
            edited = bot.get_message(msg_id)
            assert OnboardingTemplates.instructions() in edited.text

    async def test_happy_path_starts_onboarding(self, mocks: MockHolder):
        """Line 134: valid code → instructions + keyboard + state=instructions."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course()
        mocks.user_repo.get_by_id.return_value = _make_user(telegram_id=None)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "TESTCODE")
            bot.assert_last_bot_message_contains("Что тебя ждёт")
            state = await _get_fsm_state(dp, bot.user_id, bot.chat_id)
            assert state == OnboardingStates.instructions.state

    async def test_fsm_data_stored_correctly(self, mocks: MockHolder):
        """Lines 140-147: all FSM fields set after /start."""
        course = _make_course(id=42, user_id=10)
        user = _make_user(id=10, manager_id=5, name="Иванова Мария")
        mocks.course_repo.get_by_invite_code.return_value = course
        mocks.user_repo.get_by_id.return_value = user
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _send_start(bot, "CODE")
            data = await _get_fsm_data(dp, bot.user_id, bot.chat_id)
            assert data["course_id"] == 42
            assert data["user_id"] == 10
            assert data["manager_id"] == 5
            assert data["user_name"] == "Иванова Мария"
            assert data["course_created_date"] == "2025-01-15"
            assert "bot_message_id" in data

    async def test_new_course_replaces_different_onboarding(self, mocks: MockHolder):
        """Line 128: in onboarding with DIFFERENT course_id → start new onboarding."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course(id=99)
        mocks.user_repo.get_by_id.return_value = _make_user(telegram_id=USER_ID)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "old text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(msg_id, course_id=1),  # old course_id=1
            )
            await _send_start(bot, "TESTCODE")
            # New onboarding started (course_id=99 != 1)
            data = await _get_fsm_data(dp, bot.user_id, bot.chat_id)
            assert data["course_id"] == 99


# ── TestOnInstructionsUnderstood ──────────────────────────────────────────


class TestOnInstructionsUnderstood:
    """Tests for on_instructions_understood (lines 159-176)."""

    async def test_happy_path(self, mocks: MockHolder):
        """Click 'Понятно' → edit to cycle_day, state → cycle_day."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, OnboardingTemplates.instructions())
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(msg_id),
            )
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            edited = bot.get_message(msg_id)
            assert OnboardingTemplates.cycle_day() in edited.text
            state = await _get_fsm_state(dp, bot.user_id, bot.chat_id)
            assert state == OnboardingStates.cycle_day.state
            assert bot.get_callback_answers()

    async def test_expired_stops_flow(self, mocks: MockHolder):
        """Expired link → edit to expired message, state cleared."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(msg_id, course_created_date=YESTERDAY.isoformat()),
            )
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            edited = bot.get_message(msg_id)
            assert "должна была зарегистрироваться" in edited.text
            state = await _get_fsm_state(dp, bot.user_id, bot.chat_id)
            assert state is None
            mocks.course_repo.set_expired.assert_called_once_with(1)

    async def test_no_course_id_session_expired(self, mocks: MockHolder):
        """No course_id in FSM data → 'Сессия истекла' alert."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                {"bot_message_id": msg_id},  # no course_id!
            )
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            answers = bot.get_callback_answers()
            assert any("Сессия истекла" in (a.data.get("text") or "") for a in answers)
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None


# ── TestOnCycleDaySelected ────────────────────────────────────────────────


class TestOnCycleDaySelected:
    """Tests for on_cycle_day_selected (lines 184-211)."""

    async def test_happy_path_day_1(self, mocks: MockHolder):
        """Select day 1 → edit to intake_time, state → intake_time."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, OnboardingTemplates.cycle_day())
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.cycle_day,
                _base_fsm_data(msg_id),
            )
            await bot.click_button(CB_DAY_1, msg_id)

            edited = bot.get_message(msg_id)
            assert OnboardingTemplates.intake_time() in edited.text
            state = await _get_fsm_state(dp, bot.user_id, bot.chat_id)
            assert state == OnboardingStates.intake_time.state

    async def test_happy_path_day_4(self, mocks: MockHolder):
        """Boundary: day=4 works correctly."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.cycle_day,
                _base_fsm_data(msg_id),
            )
            await bot.click_button(CB_DAY_4, msg_id)

            data = await _get_fsm_data(dp, bot.user_id, bot.chat_id)
            assert data["cycle_day"] == 4

    async def test_no_slots_late_night(self, mocks: MockHolder):
        """23:50 → no time slots → 'Слишком поздно' alert, state unchanged."""
        late_now = datetime(2025, 1, 15, 23, 50, 0, tzinfo=TASHKENT_TZ)
        with patch("keyboards.onboarding.get_tashkent_now", return_value=late_now):
            dp = await create_test_dispatcher(mocks)
            async with MockTelegramBot(dp) as bot:
                msg_id = _inject_bot_message(bot, "text")
                await _set_fsm(
                    dp, bot.user_id, bot.chat_id,
                    OnboardingStates.cycle_day,
                    _base_fsm_data(msg_id),
                )
                await bot.click_button(CB_DAY_1, msg_id)

                answers = bot.get_callback_answers()
                assert any("Слишком поздно" in (a.data.get("text") or "") for a in answers)
                # State should NOT change to intake_time
                state = await _get_fsm_state(dp, bot.user_id, bot.chat_id)
                assert state == OnboardingStates.cycle_day.state

    async def test_expired_stops_flow(self, mocks: MockHolder):
        """Expired link at this step → expired message."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.cycle_day,
                _base_fsm_data(msg_id, course_created_date=YESTERDAY.isoformat()),
            )
            await bot.click_button(CB_DAY_1, msg_id)

            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_cycle_day_saved_to_fsm(self, mocks: MockHolder):
        """cycle_day stored in FSM data."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.cycle_day,
                _base_fsm_data(msg_id),
            )
            await bot.click_button(CB_DAY_1, msg_id)

            data = await _get_fsm_data(dp, bot.user_id, bot.chat_id)
            assert data["cycle_day"] == 1


# ── TestOnTimeSelected ────────────────────────────────────────────────────


class TestOnTimeSelected:
    """Tests for on_time_selected (lines 219-242)."""

    async def test_happy_path(self, mocks: MockHolder):
        """Select time → edit to rules with time and date."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.intake_time,
                _base_fsm_data(msg_id, cycle_day=1),
            )
            await bot.click_button(CB_TIME_1430, msg_id)

            edited = bot.get_message(msg_id)
            assert "Правила программы" in edited.text
            assert "14:30" in edited.text
            state = await _get_fsm_state(dp, bot.user_id, bot.chat_id)
            assert state == OnboardingStates.rules.state

    async def test_dash_to_colon_conversion(self, mocks: MockHolder):
        """value '14-30' → FSM data intake_time='14:30'."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.intake_time,
                _base_fsm_data(msg_id, cycle_day=1),
            )
            await bot.click_button(CB_TIME_1430, msg_id)

            data = await _get_fsm_data(dp, bot.user_id, bot.chat_id)
            assert data["intake_time"] == "14:30"

    async def test_start_date_is_today(self, mocks: MockHolder):
        """start_date saved as today DD.MM.YYYY."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.intake_time,
                _base_fsm_data(msg_id, cycle_day=1),
            )
            await bot.click_button(CB_TIME_1430, msg_id)

            data = await _get_fsm_data(dp, bot.user_id, bot.chat_id)
            assert data["start_date"] == "15.01.2025"

    async def test_expired_stops_flow(self, mocks: MockHolder):
        """Expired link at time step."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.intake_time,
                _base_fsm_data(msg_id, course_created_date=YESTERDAY.isoformat()),
            )
            await bot.click_button(CB_TIME_1430, msg_id)

            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None


# ── TestOnRulesOk ─────────────────────────────────────────────────────────


class TestOnRulesOk:
    """Tests for on_rules_ok (lines 250-272)."""

    async def test_happy_path(self, mocks: MockHolder):
        """Click Понятно → remove keyboard from msg1, send new msg2 with accept."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "rules text", {"inline_keyboard": [[]]})
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.rules,
                _base_fsm_data(msg_id, cycle_day=1, intake_time="14:30", start_date="15.01.2025"),
            )
            await bot.click_button(CB_RULES_OK, msg_id)

            # msg1 keyboard removed
            edited = bot.get_message(msg_id)
            assert edited.reply_markup is None or edited.reply_markup == {}
            # New message sent with bot_instructions
            bot_msgs = bot.get_bot_messages()
            new_msg = [m for m in bot_msgs if m.message_id != msg_id]
            assert len(new_msg) == 1
            assert OnboardingTemplates.bot_instructions() in new_msg[0].text

    async def test_instructions_message_id_saved(self, mocks: MockHolder):
        """instructions_message_id saved to FSM."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "rules text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.rules,
                _base_fsm_data(msg_id, cycle_day=1, intake_time="14:30", start_date="15.01.2025"),
            )
            await bot.click_button(CB_RULES_OK, msg_id)

            data = await _get_fsm_data(dp, bot.user_id, bot.chat_id)
            assert "instructions_message_id" in data
            assert data["instructions_message_id"] != msg_id

    async def test_state_changes_to_accept_terms(self, mocks: MockHolder):
        """State → accept_terms."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "rules text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.rules,
                _base_fsm_data(msg_id, cycle_day=1, intake_time="14:30", start_date="15.01.2025"),
            )
            await bot.click_button(CB_RULES_OK, msg_id)

            state = await _get_fsm_state(dp, bot.user_id, bot.chat_id)
            assert state == OnboardingStates.accept_terms.state

    async def test_expired_stops_flow(self, mocks: MockHolder):
        """Expired link at rules step."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.rules,
                _base_fsm_data(msg_id, course_created_date=YESTERDAY.isoformat()),
            )
            await bot.click_button(CB_RULES_OK, msg_id)

            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_callback_answered(self, mocks: MockHolder):
        """callback.answer() called."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.rules,
                _base_fsm_data(msg_id, cycle_day=1, intake_time="14:30", start_date="15.01.2025"),
            )
            await bot.click_button(CB_RULES_OK, msg_id)

            assert bot.get_callback_answers()


# ── TestOnAcceptTerms ─────────────────────────────────────────────────────


class TestOnAcceptTerms:
    """Tests for on_accept_terms (lines 280-470) — most complex handler."""

    def _accept_fsm_data(self, bot_msg_id: int, instr_msg_id: int, **extra) -> dict:
        """FSM data for accept_terms step."""
        return _base_fsm_data(
            bot_msg_id,
            cycle_day=2,
            intake_time="14:30",
            start_date="15.01.2025",
            instructions_message_id=instr_msg_id,
            **extra,
        )

    async def test_full_happy_path(self, mocks: MockHolder):
        """Full finalization: activate → topic → card → video → pin → clear."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "bot instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            # DB: activate called
            mocks.course_repo.activate.assert_called_once()
            # Topic created in group
            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert len(topics) == 1
            # State cleared
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_double_click_blocked(self, mocks: MockHolder):
        """Button removed immediately, second click has no button to press."""
        mocks.course_repo.activate.return_value = True
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            # Button removed (edit_reply_markup called)
            markup_edits = bot.get_edited_markups()
            assert len(markup_edits) >= 1

    async def test_missing_fsm_key(self, mocks: MockHolder):
        """Missing user_id in FSM → KeyError → error alert + state.clear()."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            # Include course_id and course_created_date (needed by _check_expiration_callback)
            # but omit user_id to trigger KeyError in on_accept_terms
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                {
                    "bot_message_id": msg_id,
                    "course_created_date": TODAY.isoformat(),
                    "course_id": 1,
                },
            )
            await bot.click_button(CB_ACCEPT, msg_id)

            answers = bot.get_callback_answers()
            assert any("Ошибка" in (a.data.get("text") or "") for a in answers)
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_activate_exception(self, mocks: MockHolder):
        """activate() raises → error alert."""
        mocks.course_repo.activate.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            answers = bot.get_callback_answers()
            assert any("Ошибка" in (a.data.get("text") or "") for a in answers)

    async def test_activate_returns_false(self, mocks: MockHolder):
        """Already activated (race condition) → silent finish, state cleared."""
        mocks.course_repo.activate.return_value = False
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            # No alarming popup — just silent callback answer
            answers = bot.get_callback_answers()
            assert all(not a.data.get("text") for a in answers)
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_expired_stops_finalization(self, mocks: MockHolder):
        """Expired link at accept step."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                _base_fsm_data(msg_id, course_created_date=YESTERDAY.isoformat()),
            )
            await bot.click_button(CB_ACCEPT, msg_id)

            mocks.course_repo.activate.assert_not_called()

    async def test_topic_created_with_icon(self, mocks: MockHolder):
        """Forum topic created with custom emoji icon."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert len(topics) == 1
            assert topics[0].icon_custom_emoji_id == "5235579393115438657"

    async def test_topic_fallback_no_icon(self, mocks: MockHolder):
        """TelegramBadRequest on icon → retry without icon → success."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            # First createForumTopic fails, second succeeds
            original_route = bot._server._route_method
            calls = []

            def patched(method, data):
                if method == "createForumTopic":
                    calls.append(data)
                    if len(calls) == 1:
                        return {"ok": False, "error_code": 400, "description": "Bad Request: invalid emoji"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.click_button(CB_ACCEPT, msg2_id)

            assert len(calls) == 2
            # First call had icon, second did not
            assert "icon_custom_emoji_id" in calls[0]
            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert len(topics) == 1

    async def test_topic_total_failure(self, mocks: MockHolder):
        """Both topic creation attempts fail → topic_id=0, no card sent."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "createForumTopic":
                    return {"ok": False, "error_code": 400, "description": "Bad Request: error"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.click_button(CB_ACCEPT, msg2_id)

            # No topic created, no card in group
            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert len(topics) == 0
            group_msgs = bot.get_thread_messages(KOK_GROUP_ID, 0)
            assert len(group_msgs) == 0
            # set_topic_id NOT called with 0
            mocks.user_repo.set_topic_id.assert_not_called()

    async def test_registration_card_sent(self, mocks: MockHolder):
        """Card sent to group topic with correct text."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            topic_id = topics[0].message_thread_id
            thread_msgs = bot.get_thread_messages(KOK_GROUP_ID, topic_id)
            assert len(thread_msgs) >= 1
            card_msg = thread_msgs[0]
            assert "Иванова Мария Петровна" in card_msg.text
            assert "14:30" in card_msg.text

    async def test_card_has_keyboard(self, mocks: MockHolder):
        """Registration card has extend/complete buttons."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            topic_id = topics[0].message_thread_id
            thread_msgs = bot.get_thread_messages(KOK_GROUP_ID, topic_id)
            card = thread_msgs[0]
            assert card.reply_markup is not None
            buttons = [b["text"] for row in card.reply_markup["inline_keyboard"] for b in row]
            assert "Продлить +21 день" in buttons

    async def test_card_send_fails(self, mocks: MockHolder):
        """Card send fails → flow continues, registration_message_id not saved."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "sendMessage" and data.get("message_thread_id"):
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.click_button(CB_ACCEPT, msg2_id)

            mocks.course_repo.set_registration_message_id.assert_not_called()
            # Flow still completes
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_topic_id_saved(self, mocks: MockHolder):
        """set_topic_id called with correct args."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            mocks.user_repo.set_topic_id.assert_called_once()
            call_args = mocks.user_repo.set_topic_id.call_args
            assert call_args[0][0] == 10  # user_id

    async def test_registration_msg_id_saved(self, mocks: MockHolder):
        """set_registration_message_id called."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            mocks.course_repo.set_registration_message_id.assert_called_once()

    async def test_db_save_fails_continues(self, mocks: MockHolder):
        """set_topic_id/set_registration_message_id fail → flow continues."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        mocks.user_repo.set_topic_id.side_effect = Exception("DB error")
        mocks.course_repo.set_registration_message_id.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            # Flow still completes despite DB errors
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_tutorial_video_sent(self, mocks: MockHolder):
        """Tutorial video sent to private chat."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            video_reqs = bot._server.tracker.get_send_video_requests()
            assert len(video_reqs) >= 1

    async def test_video_fails_text_fallback(self, mocks: MockHolder):
        """Video send fails → fallback to text-only message."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "sendVideo":
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.click_button(CB_ACCEPT, msg2_id)

            # Fallback: text message with tutorial caption
            sent = bot.get_sent_messages()
            texts = [s.data.get("text", "") for s in sent]
            assert any("Как снимать видео" in t for t in texts)

    async def test_no_pins_sent(self, mocks: MockHolder):
        """Messages are NOT pinned (pins removed)."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            pin_reqs = bot._server.tracker.get_requests_by_method("pinChatMessage")
            assert len(pin_reqs) == 0

    async def test_name_parsing_full(self, mocks: MockHolder):
        """'Иванова Мария Петровна' → topic 'Иванова М.П. (Алина) 0/21'."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager(name="Алина")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id, user_name="Иванова Мария Петровна"),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert "Иванова М.П." in topics[0].name
            assert "(Алина)" in topics[0].name
            assert "0/21" in topics[0].name

    async def test_name_parsing_short(self, mocks: MockHolder):
        """'Иванова' → topic 'Иванова (Алина) 0/21'."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager(name="Алина")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id, user_name="Иванова"),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert "Иванова" in topics[0].name
            assert "0/21" in topics[0].name

    async def test_name_parsing_two_parts(self, mocks: MockHolder):
        """'Иванова Мария' (no patronymic) → topic without 'П.'."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager(name="Алина")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id, user_name="Иванова Мария"),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert "Иванова М." in topics[0].name
            assert "П." not in topics[0].name

    async def test_name_parsing_empty(self, mocks: MockHolder):
        """Empty user_name → last_name='Unknown'."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id, user_name=""),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert "Unknown" in topics[0].name

    async def test_manager_not_found(self, mocks: MockHolder):
        """manager_repo.get_by_id returns None → topic uses 'Manager'."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert "(Manager)" in topics[0].name

    async def test_manager_repo_exception(self, mocks: MockHolder):
        """manager_repo.get_by_id raises → topic uses 'Manager', flow continues."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert "(Manager)" in topics[0].name
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_topic_creation_server_error(self, mocks: MockHolder):
        """500 error on createForumTopic → except Exception (line 389) → topic_id=0."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "createForumTopic":
                    return {"ok": False, "error_code": 500, "description": "Internal Server Error"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.click_button(CB_ACCEPT, msg2_id)

            topics = bot.get_forum_topics(KOK_GROUP_ID)
            assert len(topics) == 0
            mocks.user_repo.set_topic_id.assert_not_called()
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_video_and_text_fallback_both_fail(self, mocks: MockHolder):
        """sendVideo fails AND text fallback fails → video_msg=None, flow continues."""
        mocks.course_repo.activate.return_value = True
        mocks.manager_repo.get_by_id.return_value = _make_manager()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg1_id = _inject_bot_message(bot, "rules")
            msg2_id = _inject_bot_message(bot, "instructions")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                self._accept_fsm_data(msg1_id, msg2_id),
            )
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "sendVideo":
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                if method == "sendMessage" and "Как снимать видео" in data.get("text", ""):
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.click_button(CB_ACCEPT, msg2_id)

            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None


# ── TestOnSpamDuringOnboarding ────────────────────────────────────────────


class TestOnSpamDuringOnboarding:
    """Tests for on_spam_during_onboarding (lines 478-492)."""

    async def test_spam_deleted_and_hint_sent(self, mocks: MockHolder):
        """Spam message deleted, 'Выбери одну из кнопок' sent."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(0),
            )
            await bot.send_message("random text")

            # Spam deleted
            user_msgs = bot.get_user_messages(include_deleted=True)
            assert any(m.is_deleted for m in user_msgs)
            # Hint sent
            bot.assert_last_bot_message_contains(OnboardingTemplates.use_buttons())

    async def test_delete_fails_still_sends_hint(self, mocks: MockHolder):
        """Delete fails → hint still sent."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(0),
            )
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "deleteMessage":
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_message("spam")

            bot.assert_last_bot_message_contains(OnboardingTemplates.use_buttons())

    async def test_works_in_all_five_states(self, mocks: MockHolder):
        """Spam handler active in all 5 onboarding states."""
        states = [
            OnboardingStates.instructions,
            OnboardingStates.cycle_day,
            OnboardingStates.intake_time,
            OnboardingStates.rules,
            OnboardingStates.accept_terms,
        ]
        for state in states:
            dp = await create_test_dispatcher(mocks)
            async with MockTelegramBot(dp) as bot:
                await _set_fsm(
                    dp, bot.user_id, bot.chat_id,
                    state,
                    _base_fsm_data(0),
                )
                await bot.send_message("spam")
                bot.assert_last_bot_message_contains(OnboardingTemplates.use_buttons())

    async def test_delete_generic_exception_still_sends_hint(self, mocks: MockHolder):
        """Generic Exception (not TelegramBadRequest) on delete → hint still sent."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(0),
            )
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "deleteMessage":
                    return {"ok": False, "error_code": 500, "description": "Internal Server Error"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_message("spam")

            bot.assert_last_bot_message_contains(OnboardingTemplates.use_buttons())


# ── TestOnExpiredCallback ─────────────────────────────────────────────────


class TestOnExpiredCallback:
    """Test for on_expired_callback catch-all (lines 649-654)."""

    async def test_catch_all_expired(self, mocks: MockHolder):
        """Onboarding callback without FSM state → 'Ссылка истекла' alert."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "old message")
            # NO FSM state set — catch-all should handle
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            answers = bot.get_callback_answers()
            assert any("Ссылка истекла" in (a.data.get("text") or "") for a in answers)


# ── TestCheckAndExpire ────────────────────────────────────────────────────


class TestCheckAndExpire:
    """Unit tests for _check_and_expire helper (lines 500-514)."""

    async def test_same_day_not_expired(self):
        """Course created today → False, set_expired NOT called."""
        from handlers.onboarding import _check_and_expire

        course = _make_course(created_at=datetime(2025, 1, 15, 8, 0, 0, tzinfo=TASHKENT_TZ))
        repo = AsyncMock()
        result = await _check_and_expire(course, repo)
        assert result is False
        repo.set_expired.assert_not_called()

    async def test_previous_day_expired_setup(self):
        """Course created yesterday, status=SETUP → True + set_expired called."""
        from handlers.onboarding import _check_and_expire

        course = _make_course(
            created_at=datetime(2025, 1, 14, 8, 0, 0, tzinfo=TASHKENT_TZ),
            status=CourseStatus.SETUP,
        )
        repo = AsyncMock()
        result = await _check_and_expire(course, repo)
        assert result is True
        repo.set_expired.assert_called_once_with(1)

    async def test_set_expired_exception_still_returns_true(self):
        """set_expired raises → still returns True."""
        from handlers.onboarding import _check_and_expire

        course = _make_course(
            created_at=datetime(2025, 1, 14, 8, 0, 0, tzinfo=TASHKENT_TZ),
            status=CourseStatus.SETUP,
        )
        repo = AsyncMock()
        repo.set_expired.side_effect = Exception("DB error")
        result = await _check_and_expire(course, repo)
        assert result is True

    async def test_non_setup_status_no_db_call(self):
        """status=ACTIVE, yesterday → True but set_expired NOT called."""
        from handlers.onboarding import _check_and_expire

        course = _make_course(
            created_at=datetime(2025, 1, 14, 8, 0, 0, tzinfo=TASHKENT_TZ),
            status=CourseStatus.ACTIVE,
        )
        repo = AsyncMock()
        result = await _check_and_expire(course, repo)
        assert result is True
        repo.set_expired.assert_not_called()


# ── TestCheckExpirationCallback ───────────────────────────────────────────


class TestCheckExpirationCallback:
    """Tests for _check_expiration_callback through instructions handler."""

    async def test_no_course_id_clears_state(self, mocks: MockHolder):
        """Missing course_id → 'Сессия истекла', state cleared."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                {"bot_message_id": msg_id},
            )
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            answers = bot.get_callback_answers()
            assert any("Сессия истекла" in (a.data.get("text") or "") for a in answers)
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_no_course_date_clears_state(self, mocks: MockHolder):
        """Missing course_created_date → 'Сессия истекла'."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                {"bot_message_id": msg_id, "course_id": 1},
            )
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            answers = bot.get_callback_answers()
            assert any("Сессия истекла" in (a.data.get("text") or "") for a in answers)

    async def test_same_day_passes(self, mocks: MockHolder):
        """course_date == today → not expired, handler proceeds."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "text")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(msg_id),
            )
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            # Handler proceeded — state changed to cycle_day
            state = await _get_fsm_state(dp, bot.user_id, bot.chat_id)
            assert state == OnboardingStates.cycle_day.state

    async def test_expired_edits_message_and_clears(self, mocks: MockHolder):
        """Expired → message edited to expired text, set_expired called, state cleared."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "original")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(msg_id, course_created_date=YESTERDAY.isoformat()),
            )
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            edited = bot.get_message(msg_id)
            assert "должна была зарегистрироваться" in edited.text
            mocks.course_repo.set_expired.assert_called_once_with(1)
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_set_expired_exception_continues(self, mocks: MockHolder):
        """set_expired raises → flow still continues (edit + clear)."""
        mocks.course_repo.set_expired.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "original")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(msg_id, course_created_date=YESTERDAY.isoformat()),
            )
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            edited = bot.get_message(msg_id)
            assert "должна была зарегистрироваться" in edited.text
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None

    async def test_edit_text_fails_still_clears(self, mocks: MockHolder):
        """edit_text raises TelegramBadRequest → pass, state still cleared."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "original")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(msg_id, course_created_date=YESTERDAY.isoformat()),
            )
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "editMessageText":
                    return {"ok": False, "error_code": 400, "description": "Bad Request: message not found"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.click_button(CB_UNDERSTOOD, msg_id)

            # State cleared even though edit failed
            assert await _get_fsm_state(dp, bot.user_id, bot.chat_id) is None
            mocks.course_repo.set_expired.assert_called_once_with(1)


# ── TestResendCurrentStep ─────────────────────────────────────────────────


class TestResendCurrentStep:
    """Tests for _resend_current_step via /start re-click (lines 554-625)."""

    def _setup_mocks(self, mocks: MockHolder) -> None:
        """Common mock setup for resend tests."""
        mocks.course_repo.get_by_invite_code.return_value = _make_course()
        mocks.user_repo.get_by_id.return_value = _make_user(telegram_id=USER_ID)

    async def test_resend_instructions(self, mocks: MockHolder):
        """state=instructions → edit to instructions text."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "old")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(msg_id),
            )
            await _send_start(bot, "TESTCODE")

            edited = bot.get_message(msg_id)
            assert OnboardingTemplates.instructions() in edited.text

    async def test_resend_cycle_day(self, mocks: MockHolder):
        """state=cycle_day → edit to cycle_day text."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "old")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.cycle_day,
                _base_fsm_data(msg_id),
            )
            await _send_start(bot, "TESTCODE")

            edited = bot.get_message(msg_id)
            assert OnboardingTemplates.cycle_day() in edited.text

    async def test_resend_intake_time_with_slots(self, mocks: MockHolder):
        """state=intake_time, slots available → edit to intake_time text."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "old")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.intake_time,
                _base_fsm_data(msg_id, cycle_day=1),
            )
            await _send_start(bot, "TESTCODE")

            edited = bot.get_message(msg_id)
            assert OnboardingTemplates.intake_time() in edited.text

    async def test_resend_intake_time_no_slots_rollback(self, mocks: MockHolder):
        """state=intake_time, no slots → rollback to cycle_day."""
        self._setup_mocks(mocks)
        late_now = datetime(2025, 1, 15, 23, 50, 0, tzinfo=TASHKENT_TZ)
        with patch("keyboards.onboarding.get_tashkent_now", return_value=late_now):
            dp = await create_test_dispatcher(mocks)
            async with MockTelegramBot(dp) as bot:
                msg_id = _inject_bot_message(bot, "old")
                await _set_fsm(
                    dp, bot.user_id, bot.chat_id,
                    OnboardingStates.intake_time,
                    _base_fsm_data(msg_id, cycle_day=1),
                )
                await _send_start(bot, "TESTCODE")

                edited = bot.get_message(msg_id)
                assert OnboardingTemplates.cycle_day() in edited.text
                state = await _get_fsm_state(dp, bot.user_id, bot.chat_id)
                assert state == OnboardingStates.cycle_day.state

    async def test_resend_rules(self, mocks: MockHolder):
        """state=rules → edit to rules text with time and date."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "old")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.rules,
                _base_fsm_data(msg_id, intake_time="14:30", start_date="15.01.2025"),
            )
            await _send_start(bot, "TESTCODE")

            edited = bot.get_message(msg_id)
            assert "Правила программы" in edited.text
            assert "14:30" in edited.text

    async def test_resend_accept_terms_edit_markup(self, mocks: MockHolder):
        """state=accept_terms, instructions_msg_id exists → edit_reply_markup."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "rules")
            instr_id = _inject_bot_message(bot, "instructions", {"inline_keyboard": []})
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                _base_fsm_data(msg_id, instructions_message_id=instr_id),
            )
            await _send_start(bot, "TESTCODE")

            edited = bot.get_message(instr_id)
            assert edited.reply_markup is not None
            kb = edited.reply_markup.get("inline_keyboard", [])
            button_texts = [b["text"] for row in kb for b in row]
            assert "Принимаю условия" in button_texts

    async def test_resend_accept_terms_edit_fails_send_new(self, mocks: MockHolder):
        """edit_reply_markup fails → send new message."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "rules")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                _base_fsm_data(msg_id, instructions_message_id=99999),  # non-existent
            )
            await _send_start(bot, "TESTCODE")

            # New message sent with bot_instructions
            bot_msgs = bot.get_bot_messages()
            new_msgs = [m for m in bot_msgs if m.message_id != msg_id]
            assert any(OnboardingTemplates.bot_instructions() in (m.text or "") for m in new_msgs)

    async def test_resend_accept_terms_no_msg_id(self, mocks: MockHolder):
        """No instructions_message_id → send new message."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "rules")
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.accept_terms,
                _base_fsm_data(msg_id),  # no instructions_message_id
            )
            await _send_start(bot, "TESTCODE")

            bot_msgs = bot.get_bot_messages()
            new_msgs = [m for m in bot_msgs if m.message_id != msg_id]
            assert any(OnboardingTemplates.bot_instructions() in (m.text or "") for m in new_msgs)

    async def test_edit_fails_send_new_fallback(self, mocks: MockHolder):
        """Edit existing bot_message_id fails → send new + update FSM."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.instructions,
                _base_fsm_data(99999),  # non-existent message
            )
            await _send_start(bot, "TESTCODE")

            # New message sent as fallback
            bot_msgs = bot.get_bot_messages()
            assert any(OnboardingTemplates.instructions() in (m.text or "") for m in bot_msgs)
            # bot_message_id updated in FSM
            data = await _get_fsm_data(dp, bot.user_id, bot.chat_id)
            assert data["bot_message_id"] != 99999

    async def test_unknown_state_noop(self, mocks: MockHolder):
        """Unknown FSM state → return (no message sent)."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            msg_id = _inject_bot_message(bot, "old")
            # Manually set a state that _resend_current_step doesn't know
            key = StorageKey(bot_id=BOT_ID, chat_id=bot.chat_id, user_id=bot.user_id)
            await dp.storage.set_state(key, "OnboardingStates:unknown_state")
            await dp.storage.set_data(key, _base_fsm_data(msg_id))

            await _send_start(bot, "TESTCODE")

            # No edit or new message for this state — new onboarding starts
            # because current_state doesn't start with "OnboardingStates:"?
            # Actually "OnboardingStates:unknown_state" DOES start with "OnboardingStates:"
            # and course_id matches, so _resend_current_step is called
            # But unknown state_name not in state_to_text → return (nothing sent for resend)
            # The message should remain unchanged
            edited = bot.get_message(msg_id)
            assert edited.text == "old"

    async def test_no_bot_message_id_send_new(self, mocks: MockHolder):
        """bot_message_id=None → send new message."""
        self._setup_mocks(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await _set_fsm(
                dp, bot.user_id, bot.chat_id,
                OnboardingStates.cycle_day,
                _base_fsm_data(0),  # bot_message_id=0 (falsy)
            )
            await _send_start(bot, "TESTCODE")

            bot_msgs = bot.get_bot_messages()
            assert any(OnboardingTemplates.cycle_day() in (m.text or "") for m in bot_msgs)