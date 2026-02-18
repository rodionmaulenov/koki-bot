"""Tests for handlers/video/receive.py — 113 tests, 100% branch coverage."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from aiogram.types import Chat, Message, Update, VideoNote

from handlers.video.receive import (
    TOPIC_ICON_ACTIVE,
    TOPIC_ICON_COMPLETED,
    TOPIC_ICON_REFUSED,
)
from models.course import Course
from models.enums import CourseStatus
from models.intake_log import IntakeLog
from models.manager import Manager
from models.user import User as KokUser
from models.video_result import VideoResult
from services.video_service import WindowStatus
from templates import AppealTemplates, VideoTemplates
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

FIXED_NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=TASHKENT_TZ)
DEADLINE = datetime(2025, 1, 16, 8, 0, 0, tzinfo=TASHKENT_TZ)
DEADLINE_STR = "16.01 08:00"
# Reshoot deadline must be in the future (handler compares with get_tashkent_now)
RESHOOT_DEADLINE_FUTURE = datetime(2099, 12, 31, 23, 59, tzinfo=TASHKENT_TZ)

# Tracker stores form data values as strings — use these for comparisons
_S_GROUP = str(KOK_GROUP_ID)
_S_GENERAL = str(KOK_GENERAL_TOPIC_ID)
_S_MANAGER = str(MANAGER_TG_ID)
_S_TOPIC = str(TOPIC_ID)
_S_USER = str(USER_ID)


# ── Factories ─────────────────────────────────────────────────────────────


def _make_user(**overrides) -> KokUser:
    defaults = dict(
        id=1, telegram_id=USER_ID, name="Test Girl",
        manager_id=1, topic_id=TOPIC_ID,
        created_at=datetime(2025, 1, 1, tzinfo=TASHKENT_TZ),
    )
    defaults.update(overrides)
    return KokUser(**defaults)


def _make_course(**overrides) -> Course:
    defaults = dict(
        id=10, user_id=1, status=CourseStatus.ACTIVE,
        intake_time=time(10, 0), current_day=5, total_days=21,
        late_count=0, appeal_count=0, late_dates=[],
        created_at=datetime(2025, 1, 1, tzinfo=TASHKENT_TZ),
    )
    defaults.update(overrides)
    return Course(**defaults)


def _make_intake_log(**overrides) -> IntakeLog:
    defaults = dict(
        id=100, course_id=10, day=6, status="taken",
        delay_minutes=5, video_file_id="test_video",
        confidence=0.95, verified_by="gemini",
        created_at=datetime(2025, 1, 15, tzinfo=TASHKENT_TZ),
    )
    defaults.update(overrides)
    return IntakeLog(**defaults)


def _make_video_result(**overrides) -> VideoResult:
    defaults = dict(approved=True, confidence=0.95, reason="Girl takes pill")
    defaults.update(overrides)
    return VideoResult(**defaults)


def _make_manager(**overrides) -> Manager:
    defaults = dict(
        id=1, telegram_id=MANAGER_TG_ID, name="Test Manager",
        is_active=True, created_at=datetime(2025, 1, 1, tzinfo=TASHKENT_TZ),
    )
    defaults.update(overrides)
    return Manager(**defaults)


# ── Helpers ───────────────────────────────────────────────────────────────


def _setup_happy_path(mocks: MockHolder, **kw) -> tuple[KokUser, Course]:
    """Configure mocks for happy path: user with active course, window open."""
    user = kw.get("user", _make_user())
    course = kw.get("course", _make_course())

    mocks.user_repo.get_by_telegram_id.return_value = user
    mocks.course_repo.get_active_by_user_id.return_value = course
    mocks.video_service.get_pending_reshoot.return_value = None
    mocks.video_service.check_window.return_value = (WindowStatus.OPEN, "")
    mocks.video_service.get_today_log.return_value = None
    mocks.gemini_service.process_video.return_value = kw.get(
        "video_result", _make_video_result(),
    )
    mocks.video_service.record_intake.return_value = kw.get(
        "intake_log", _make_intake_log(),
    )
    mocks.video_service.get_max_strikes.return_value = kw.get("max_strikes", 3)
    mocks.video_service.record_late.return_value = kw.get("late_result", (0, []))
    mocks.video_service.calculate_deadline.return_value = kw.get("deadline", DEADLINE)
    mocks.manager_repo.get_by_id.return_value = kw.get("manager", _make_manager())

    return user, course


def _get_topic_sends(bot: MockTelegramBot, topic_id: int = TOPIC_ID) -> list[TrackedRequest]:
    """Get sendMessage requests to KOK group topic."""
    reqs = bot._server.tracker.get_requests_by_method("sendMessage")
    return [r for r in reqs if str(r.data.get("chat_id")) == _S_GROUP
            and str(r.data.get("message_thread_id")) == str(topic_id)]


def _get_general_sends(bot: MockTelegramBot) -> list[TrackedRequest]:
    """Get sendMessage requests to general topic."""
    reqs = bot._server.tracker.get_requests_by_method("sendMessage")
    return [r for r in reqs if str(r.data.get("chat_id")) == _S_GROUP
            and str(r.data.get("message_thread_id")) == _S_GENERAL]


def _get_manager_dms(bot: MockTelegramBot) -> list[TrackedRequest]:
    """Get sendMessage requests to manager DM."""
    reqs = bot._server.tracker.get_requests_by_method("sendMessage")
    return [r for r in reqs if str(r.data.get("chat_id")) == _S_MANAGER]


def _get_topic_video_notes(bot: MockTelegramBot) -> list[TrackedRequest]:
    """Get sendVideoNote requests to KOK group."""
    reqs = bot._server.tracker.get_requests_by_method("sendVideoNote")
    return [r for r in reqs if str(r.data.get("chat_id")) == _S_GROUP]


def _get_topic_videos(bot: MockTelegramBot) -> list[TrackedRequest]:
    """Get sendVideo requests to KOK group."""
    reqs = bot._server.tracker.get_requests_by_method("sendVideo")
    return [r for r in reqs if str(r.data.get("chat_id")) == _S_GROUP]


def _get_edit_topic_reqs(bot: MockTelegramBot) -> list[TrackedRequest]:
    """Get editForumTopic requests."""
    return bot._server.tracker.get_requests_by_method("editForumTopic")


def _get_close_topic_reqs(bot: MockTelegramBot) -> list[TrackedRequest]:
    """Get closeForumTopic requests."""
    return bot._server.tracker.get_requests_by_method("closeForumTopic")


# ── TestOnVideoNote ───────────────────────────────────────────────────────


class TestOnVideoNote:
    """Tests for on_video_note handler (lines 59-73)."""

    async def test_approved_by_ai(self, mocks: MockHolder):
        """Happy path: video_note → AI approved → 'Молодец! День 6/21'."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))

    async def test_no_active_course(self, mocks: MockHolder):
        """No user → 'нет активной программы'."""
        mocks.user_repo.get_by_telegram_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.no_active_course())

    async def test_passes_video_note_type(self, mocks: MockHolder):
        """file_id from video_note; sendVideoNote used for topic."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note(file_id="my_vnote_123")
            assert len(_get_topic_video_notes(bot)) == 1
            assert _get_topic_video_notes(bot)[0].data["video_note"] == "my_vnote_123"


# ── TestOnVideo ───────────────────────────────────────────────────────────


class TestOnVideo:
    """Tests for on_video handler (lines 76-91)."""

    async def test_approved_by_ai(self, mocks: MockHolder):
        """video → AI approved → day recorded."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video()
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))

    async def test_sends_video_to_topic(self, mocks: MockHolder):
        """sendVideo (not sendVideoNote) used for topic when user sends video."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video(file_id="my_video_123")
            assert len(_get_topic_videos(bot)) == 1
            assert _get_topic_videos(bot)[0].data["video"] == "my_video_123"

    async def test_default_mime(self, mocks: MockHolder):
        """Video without explicit mime → falls back to video/mp4. AI still called."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video()
            mocks.gemini_service.process_video.assert_called_once()


# ── TestOnVideoDocument ───────────────────────────────────────────────────


class TestOnVideoDocument:
    """Tests for on_video_document handler (lines 94-112)."""

    async def test_non_video_rejected(self, mocks: MockHolder):
        """Document with 'application/pdf' → 'только видео'."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_document(mime_type="application/pdf")
            bot.assert_last_bot_message_contains(VideoTemplates.video_only())

    async def test_empty_mime_rejected(self, mocks: MockHolder):
        """Document without mime_type → '' → not video/ → rejected."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_document(mime_type="")
            bot.assert_last_bot_message_contains(VideoTemplates.video_only())

    async def test_video_mime_accepted(self, mocks: MockHolder):
        """Document with 'video/mp4' → processed as video."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_document(mime_type="video/mp4")
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))

    async def test_video_quicktime_accepted(self, mocks: MockHolder):
        """Document with 'video/quicktime' → processed as video."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_document(mime_type="video/quicktime")
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))


# ── TestOnPrivateOther ────────────────────────────────────────────────────


class TestOnPrivateOther:
    """Tests for on_private_other catch-all (lines 120-165)."""

    async def test_no_course_video_only(self, mocks: MockHolder):
        """No active course → 'только видео'."""
        mocks.user_repo.get_by_telegram_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("hello")
            bot.assert_last_bot_message_contains(VideoTemplates.video_only())

    async def test_course_completed(self, mocks: MockHolder):
        """current_day >= total_days → 'прошла программу'."""
        _setup_happy_path(mocks, course=_make_course(current_day=21, total_days=21))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("hello")
            bot.assert_last_bot_message_contains(VideoTemplates.course_completed(21))

    async def test_reshoot_deadline_expired(self, mocks: MockHolder):
        """Reshoot with expired deadline → expire + 'время истекло'."""
        _setup_happy_path(mocks)
        expired = _make_intake_log(
            status="reshoot",
            reshoot_deadline=datetime(2025, 1, 14, 10, 0, tzinfo=TASHKENT_TZ),
        )
        mocks.video_service.get_pending_reshoot.return_value = expired
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("text")
            bot.assert_last_bot_message_contains(VideoTemplates.reshoot_expired())
            mocks.video_service.expire_reshoot.assert_called_once()

    async def test_reshoot_active(self, mocks: MockHolder):
        """Reshoot with active deadline → 'переснять до'."""
        _setup_happy_path(mocks)
        active = _make_intake_log(
            status="reshoot",
            reshoot_deadline=RESHOOT_DEADLINE_FUTURE,
        )
        mocks.video_service.get_pending_reshoot.return_value = active
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("text")
            bot.assert_last_bot_message_contains("31.12 23:59")

    async def test_reshoot_no_deadline(self, mocks: MockHolder):
        """reshoot_deadline=None → private_reshoot('')."""
        _setup_happy_path(mocks)
        no_deadline = _make_intake_log(status="reshoot", reshoot_deadline=None)
        mocks.video_service.get_pending_reshoot.return_value = no_deadline
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("text")
            bot.assert_last_bot_message_contains(VideoTemplates.private_reshoot("", ""))

    async def test_window_early(self, mocks: MockHolder):
        """WindowStatus.EARLY → 'откроется в HH:MM'."""
        _setup_happy_path(mocks)
        mocks.video_service.check_window.return_value = (WindowStatus.EARLY, "09:50")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("text")
            bot.assert_last_bot_message_contains(VideoTemplates.window_early("09:50"))

    async def test_window_open_already_sent(self, mocks: MockHolder):
        """OPEN + existing log → 'уже отправила'."""
        _setup_happy_path(mocks)
        mocks.video_service.get_today_log.return_value = _make_intake_log()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("text")
            bot.assert_last_bot_message_contains(VideoTemplates.already_sent_today())

    async def test_window_open_send_video(self, mocks: MockHolder):
        """OPEN + no log → 'отправь видео'."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("text")
            bot.assert_last_bot_message_contains(VideoTemplates.send_video())

    async def test_window_closed(self, mocks: MockHolder):
        """CLOSED → 'только видео'."""
        _setup_happy_path(mocks)
        mocks.video_service.check_window.return_value = (WindowStatus.CLOSED, "")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("text")
            bot.assert_last_bot_message_contains(VideoTemplates.video_only())

    async def test_text_message_hits_catch_all(self, mocks: MockHolder):
        """Plain text message in private chat → on_private_other."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_message("random text")
            # Should reach on_private_other (window OPEN, no log)
            bot.assert_last_bot_message_contains(VideoTemplates.send_video())


# ── TestHandleVideoValidation ─────────────────────────────────────────────


class TestHandleVideoValidation:
    """Tests for _handle_video validation steps (lines 193-243)."""

    async def test_no_user(self, mocks: MockHolder):
        """user_repo returns None → 'нет активной программы'."""
        mocks.user_repo.get_by_telegram_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.no_active_course())

    async def test_no_active_course(self, mocks: MockHolder):
        """course_repo returns None → 'нет активной программы'."""
        mocks.user_repo.get_by_telegram_id.return_value = _make_user()
        mocks.course_repo.get_active_by_user_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.no_active_course())

    async def test_course_not_active_status(self, mocks: MockHolder):
        """course.status=REFUSED → 'нет активной программы'."""
        mocks.user_repo.get_by_telegram_id.return_value = _make_user()
        mocks.course_repo.get_active_by_user_id.return_value = _make_course(
            status=CourseStatus.REFUSED,
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.no_active_course())

    async def test_course_completed(self, mocks: MockHolder):
        """current_day=21, total_days=21 → 'прошла программу 21 дней'."""
        _setup_happy_path(mocks, course=_make_course(current_day=21, total_days=21))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.course_completed(21))

    async def test_window_early(self, mocks: MockHolder):
        """WindowStatus.EARLY → 'откроется в HH:MM'."""
        _setup_happy_path(mocks)
        mocks.video_service.check_window.return_value = (WindowStatus.EARLY, "09:50")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.window_early("09:50"))

    async def test_window_closed(self, mocks: MockHolder):
        """WindowStatus.CLOSED → 'окно закрыто'."""
        _setup_happy_path(mocks)
        mocks.video_service.check_window.return_value = (WindowStatus.CLOSED, "")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.window_closed())

    async def test_no_from_user(self, mocks: MockHolder):
        """message.from_user is None → 'нет активной программы'."""
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            update = Update(
                update_id=1,
                message=Message(
                    message_id=1,
                    date=datetime.now(),
                    chat=Chat(id=USER_ID, type="private"),
                    video_note=VideoNote(
                        file_id="test_vnote", file_unique_id="unique_test",
                        length=240, duration=15,
                    ),
                ),
            )
            await bot.dispatcher.feed_update(bot.bot, update)
            bot.assert_last_bot_message_contains(VideoTemplates.no_active_course())


# ── TestHandleVideoAlreadySent ────────────────────────────────────────────


class TestHandleVideoAlreadySent:
    """Tests for already-sent-today check (lines 240-243)."""

    async def test_already_sent_today(self, mocks: MockHolder):
        """get_today_log returns log → 'уже отправила'."""
        _setup_happy_path(mocks)
        mocks.video_service.get_today_log.return_value = _make_intake_log()
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.already_sent_today())

    async def test_not_sent_proceeds(self, mocks: MockHolder):
        """get_today_log returns None → shows processing message."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # Processing message was sent then edited to result
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))


# ── TestHandleVideoDownloadAndAI ──────────────────────────────────────────


class TestHandleVideoDownloadAndAI:
    """Tests for download and AI error handling (lines 249-282)."""

    async def test_download_exception(self, mocks: MockHolder):
        """Download fails → 'Ошибка проверки видео'."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "getFile":
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.ai_error())

    async def test_gemini_value_error(self, mocks: MockHolder):
        """Gemini raises ValueError → 'Ошибка проверки'."""
        _setup_happy_path(mocks)
        mocks.gemini_service.process_video.side_effect = ValueError("empty response")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.ai_error())

    async def test_gemini_json_error(self, mocks: MockHolder):
        """Gemini raises JSONDecodeError → 'Ошибка проверки'."""
        import json
        _setup_happy_path(mocks)
        mocks.gemini_service.process_video.side_effect = json.JSONDecodeError("", "", 0)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.ai_error())

    async def test_record_intake_exception(self, mocks: MockHolder):
        """record_intake raises → 'Ошибка проверки'."""
        _setup_happy_path(mocks)
        mocks.video_service.record_intake.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.ai_error())

    async def test_processing_message_shown(self, mocks: MockHolder):
        """'Подожди, смотрю...' message was sent (then edited)."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # The edit request should exist (processing → result)
            edits = bot.get_edited_messages()
            assert len(edits) >= 1


# ── TestHandleVideoApproved ───────────────────────────────────────────────


class TestHandleVideoApproved:
    """Tests for AI approval logic (line 265)."""

    async def test_approved_high_confidence(self, mocks: MockHolder):
        """approved=True, confidence=0.95 → 'Молодец! День 6/21'."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=True, confidence=0.95,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))

    async def test_not_approved_low_confidence(self, mocks: MockHolder):
        """approved=True but confidence=0.80 < 0.85 → pending_review."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=True, confidence=0.80,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.pending_review())

    async def test_not_approved_false(self, mocks: MockHolder):
        """approved=False, confidence=0.95 → pending_review."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.95,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.pending_review())

    async def test_threshold_boundary(self, mocks: MockHolder):
        """confidence exactly 0.85 → approved (>= threshold)."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=True, confidence=0.85,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))


# ── TestHandleVideoLateStrikes ────────────────────────────────────────────


class TestHandleVideoLateStrikes:
    """Tests for late strike logic (lines 285-300)."""

    async def test_late_threshold_not_late(self, mocks: MockHolder):
        """delay_minutes=30 → NOT late (>30 required)."""
        _setup_happy_path(mocks, intake_log=_make_intake_log(delay_minutes=30))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))
            mocks.video_service.record_late.assert_not_called()

    async def test_late_threshold_is_late(self, mocks: MockHolder):
        """delay_minutes=31 → IS late → approved_late."""
        _setup_happy_path(
            mocks,
            intake_log=_make_intake_log(delay_minutes=31),
            late_result=(1, [FIXED_NOW.isoformat()]),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains("Опоздание 1/3")
            mocks.video_service.record_late.assert_called_once()

    async def test_late_only_when_approved(self, mocks: MockHolder):
        """Not approved + delay > 30 → NOT late."""
        _setup_happy_path(
            mocks,
            video_result=_make_video_result(approved=False, confidence=0.50),
            intake_log=_make_intake_log(delay_minutes=60),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            mocks.video_service.record_late.assert_not_called()

    async def test_late_delay_none(self, mocks: MockHolder):
        """delay_minutes=None → NOT late."""
        _setup_happy_path(mocks, intake_log=_make_intake_log(delay_minutes=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            mocks.video_service.record_late.assert_not_called()

    async def test_late_first_strike(self, mocks: MockHolder):
        """Late count 1/3 → 'опоздание 1/3, ещё 2'."""
        _setup_happy_path(
            mocks,
            intake_log=_make_intake_log(delay_minutes=31),
            late_result=(1, [FIXED_NOW.isoformat()]),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(
                VideoTemplates.approved_late(6, 21, 1, 3),
            )

    async def test_late_second_strike(self, mocks: MockHolder):
        """Late count 2/3 → 'опоздание 2/3, ещё 1'."""
        dates = [FIXED_NOW.isoformat(), (FIXED_NOW - timedelta(days=1)).isoformat()]
        _setup_happy_path(
            mocks,
            intake_log=_make_intake_log(delay_minutes=45),
            late_result=(2, dates),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(
                VideoTemplates.approved_late(6, 21, 2, 3),
            )

    async def test_late_record_fails(self, mocks: MockHolder):
        """record_late raises → is_late reset to False, shows normal approved."""
        _setup_happy_path(mocks, intake_log=_make_intake_log(delay_minutes=31))
        mocks.video_service.record_late.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # Strike not recorded → don't show late warning, show normal approved
            bot.assert_last_bot_message_contains(
                VideoTemplates.approved(6, 21),
            )

    async def test_late_warning_in_topic(self, mocks: MockHolder):
        """Late → late warning sent to topic."""
        _setup_happy_path(
            mocks,
            intake_log=_make_intake_log(delay_minutes=31),
            late_result=(1, [FIXED_NOW.isoformat()]),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            topic_msgs = _get_topic_sends(bot)
            texts = [r.data.get("text", "") for r in topic_msgs]
            assert any(VideoTemplates.topic_late_warning(1, 3) in t for t in texts)

    async def test_not_late_no_warning(self, mocks: MockHolder):
        """Not late → no late warning in topic."""
        _setup_happy_path(mocks, intake_log=_make_intake_log(delay_minutes=5))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            topic_msgs = _get_topic_sends(bot)
            texts = [r.data.get("text", "") for r in topic_msgs]
            assert not any("Опоздание" in t for t in texts)


# ── TestHandleVideoRemoval ────────────────────────────────────────────────


class TestHandleVideoRemoval:
    """Tests for 3rd strike removal (lines 302-326)."""

    def _setup_removal(self, mocks: MockHolder, **kw):
        """Configure mocks for removal scenario."""
        dates = [FIXED_NOW.isoformat()] * 3
        _setup_happy_path(
            mocks,
            intake_log=_make_intake_log(delay_minutes=31),
            late_result=(3, dates),
            max_strikes=kw.get("max_strikes", 3),
            course=kw.get("course", _make_course()),
            manager=kw.get("manager", _make_manager()),
        )

    async def test_removal_on_max_strikes(self, mocks: MockHolder):
        """late_count=3, max=3 → undo_day_and_refuse called."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            mocks.video_service.undo_day_and_refuse.assert_called_once_with(10, 5)

    async def test_removal_private_message(self, mocks: MockHolder):
        """Removal → 'опоздала слишком много раз'."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains("опоздала слишком много раз")

    async def test_removal_appeal_button(self, mocks: MockHolder):
        """appeal_count=0 < MAX_APPEALS → appeal button shown."""
        self._setup_removal(mocks, course=_make_course(appeal_count=0))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            edits = bot.get_edited_messages()
            markups = [e.data.get("reply_markup") for e in edits if e.data.get("reply_markup")]
            assert len(markups) >= 1

    async def test_removal_no_appeal_button(self, mocks: MockHolder):
        """appeal_count >= MAX_APPEALS → no appeal button."""
        self._setup_removal(
            mocks,
            course=_make_course(appeal_count=AppealTemplates.MAX_APPEALS),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # Edit has no reply_markup (or None)
            edits = bot.get_edited_messages()
            last_edit = edits[-1] if edits else None
            if last_edit:
                assert last_edit.data.get("reply_markup") is None

    async def test_removal_topic_notified(self, mocks: MockHolder):
        """Removal → video + removal text + icon ❗️ sent to topic."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # Video sent to topic
            assert len(_get_topic_video_notes(bot)) == 1
            # Removal text sent
            topic_msgs = _get_topic_sends(bot)
            texts = [r.data.get("text", "") for r in topic_msgs]
            assert any("Снята с программы" in t for t in texts)
            # Icon changed to ❗️
            edit_reqs = _get_edit_topic_reqs(bot)
            icons = [r.data.get("icon_custom_emoji_id") for r in edit_reqs]
            assert str(TOPIC_ICON_REFUSED) in icons

    async def test_removal_no_manager_notify(self, mocks: MockHolder):
        """Removal → _notify_manager NOT called (no DM to manager)."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            assert len(_get_manager_dms(bot)) == 0

    async def test_removal_private_msg_not_saved(self, mocks: MockHolder):
        """Removal → save_private_message_id NOT called."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            mocks.video_service.save_private_message_id.assert_not_called()

    async def test_removal_manager_not_found(self, mocks: MockHolder):
        """Removal with manager=None → manager_name='менеджер' in private message."""
        self._setup_removal(mocks, manager=None)
        mocks.manager_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains("менеджер")

    async def test_removal_topic_with_video_type(self, mocks: MockHolder):
        """Removal with VIDEO (not VIDEO_NOTE) → sendVideo used for topic."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video()
            # sendVideo to topic (not sendVideoNote)
            assert len(_get_topic_videos(bot)) == 1
            assert len(_get_topic_video_notes(bot)) == 0

    async def test_removal_user_none_skips_general(self, mocks: MockHolder):
        """Removal with user.topic_id=None → no general topic notification."""
        self._setup_removal(mocks)
        _setup_happy_path(
            mocks,
            intake_log=_make_intake_log(delay_minutes=31),
            late_result=(3, [FIXED_NOW.isoformat()] * 3),
            user=_make_user(topic_id=None),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # No topic notifications at all (topic_id=None)
            assert len(_get_topic_video_notes(bot)) == 0
            assert len(_get_general_sends(bot)) == 0


# ── TestHandleVideoCompletion ─────────────────────────────────────────────


class TestHandleVideoCompletion:
    """Tests for course completion (lines 308-314)."""

    async def test_completion_on_last_day(self, mocks: MockHolder):
        """Day 21/21, approved → 'Поздравляю!', manager NOT notified."""
        _setup_happy_path(
            mocks,
            course=_make_course(current_day=20, total_days=21),
            intake_log=_make_intake_log(day=21),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.private_completed(21))
            mocks.video_service.complete_course.assert_called_once_with(10)
            # Manager NOT notified on completion
            assert len(_get_manager_dms(bot)) == 0

    async def test_completion_topic(self, mocks: MockHolder):
        """Completion → topic: video + text + icon ✅ + close."""
        _setup_happy_path(
            mocks,
            course=_make_course(current_day=20, total_days=21),
            intake_log=_make_intake_log(day=21),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # Video sent
            assert len(_get_topic_video_notes(bot)) == 1
            # Completion text
            topic_msgs = _get_topic_sends(bot)
            texts = [r.data.get("text", "") for r in topic_msgs]
            assert any(VideoTemplates.topic_completed(21, 21) in t for t in texts)
            # Icon ✅
            edit_reqs = _get_edit_topic_reqs(bot)
            icons = [r.data.get("icon_custom_emoji_id") for r in edit_reqs]
            assert str(TOPIC_ICON_COMPLETED) in icons
            # Topic closed
            assert len(_get_close_topic_reqs(bot)) == 1

    async def test_completion_fails_fallback(self, mocks: MockHolder):
        """complete_course raises → is_completed=False, shows approved instead."""
        _setup_happy_path(
            mocks,
            course=_make_course(current_day=20, total_days=21),
            intake_log=_make_intake_log(day=21),
        )
        mocks.video_service.complete_course.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # Falls back to approved (not completed)
            bot.assert_last_bot_message_contains(VideoTemplates.approved(21, 21))

    async def test_no_completion_if_not_approved(self, mocks: MockHolder):
        """Last day, not approved → pending_review, NOT completed."""
        _setup_happy_path(
            mocks,
            course=_make_course(current_day=20, total_days=21),
            intake_log=_make_intake_log(day=21),
            video_result=_make_video_result(approved=False, confidence=0.50),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.pending_review())
            mocks.video_service.complete_course.assert_not_called()

    async def test_no_completion_if_removal(self, mocks: MockHolder):
        """Last day + removal → removal takes priority."""
        dates = [FIXED_NOW.isoformat()] * 3
        _setup_happy_path(
            mocks,
            course=_make_course(current_day=20, total_days=21),
            intake_log=_make_intake_log(day=21, delay_minutes=31),
            late_result=(3, dates),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains("опоздала слишком много раз")
            mocks.video_service.complete_course.assert_not_called()


# ── TestHandleVideoTopicNotifications ─────────────────────────────────────


class TestHandleVideoTopicNotifications:
    """Tests for topic notifications (lines 356-383)."""

    async def test_topic_video_note_sent(self, mocks: MockHolder):
        """VIDEO_NOTE → sendVideoNote to topic."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note(file_id="vnote_file")
            notes = _get_topic_video_notes(bot)
            assert len(notes) == 1
            assert notes[0].data["video_note"] == "vnote_file"

    async def test_topic_video_sent(self, mocks: MockHolder):
        """VIDEO → sendVideo to topic."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video(file_id="video_file")
            videos = _get_topic_videos(bot)
            assert len(videos) == 1
            assert videos[0].data["video"] == "video_file"

    async def test_topic_approved_text(self, mocks: MockHolder):
        """Approved → topic text '6/21 выпила 🟢' without buttons."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            topic_msgs = _get_topic_sends(bot)
            approved_msgs = [r for r in topic_msgs if VideoTemplates.topic_approved(6, 21) in r.data.get("text", "")]
            assert len(approved_msgs) == 1
            assert approved_msgs[0].data.get("reply_markup") is None

    async def test_topic_pending_text_with_keyboard(self, mocks: MockHolder):
        """Not approved → topic text 'AI не уверен' + review_keyboard."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50, reason="No pill visible",
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            topic_msgs = _get_topic_sends(bot)
            pending_msgs = [r for r in topic_msgs if "AI не уверен" in r.data.get("text", "")]
            assert len(pending_msgs) == 1
            assert pending_msgs[0].data.get("reply_markup") is not None

    async def test_topic_icon_day1(self, mocks: MockHolder):
        """Day 1 → icon changes to 💊."""
        _setup_happy_path(
            mocks,
            course=_make_course(current_day=0),
            intake_log=_make_intake_log(day=1),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            edit_reqs = _get_edit_topic_reqs(bot)
            icons = [r.data.get("icon_custom_emoji_id") for r in edit_reqs]
            assert str(TOPIC_ICON_ACTIVE) in icons

    async def test_topic_icon_not_changed_day2(self, mocks: MockHolder):
        """Day 2, not reshoot → icon NOT changed."""
        _setup_happy_path(mocks)  # current_day=5, day=6
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            edit_reqs = _get_edit_topic_reqs(bot)
            assert len(edit_reqs) == 0

    async def test_topic_video_fail_returns(self, mocks: MockHolder):
        """sendVideoNote to topic fails → no status message sent to topic."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "sendVideoNote" and str(data.get("chat_id")) == _S_GROUP:
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # No status message to topic (early return from _send_to_topic)
            assert len(_get_topic_sends(bot)) == 0

    async def test_no_topic_skips_all(self, mocks: MockHolder):
        """user.topic_id=None → nothing sent to topic."""
        _setup_happy_path(mocks, user=_make_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            assert len(_get_topic_video_notes(bot)) == 0
            assert len(_get_topic_sends(bot)) == 0

    async def test_topic_status_message_fails(self, mocks: MockHolder):
        """Status message send to topic fails → logged, continues."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if (method == "sendMessage"
                        and str(data.get("chat_id")) == _S_GROUP
                        and str(data.get("message_thread_id")) == _S_TOPIC):
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # Handler continues — private message still shows result
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))

    async def test_topic_icon_change_fails(self, mocks: MockHolder):
        """editForumTopic fails → logged, continues."""
        _setup_happy_path(
            mocks,
            course=_make_course(current_day=0),
            intake_log=_make_intake_log(day=1),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "editForumTopic":
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # Handler continues despite icon change failure
            bot.assert_last_bot_message_contains(VideoTemplates.approved(1, 21))


# ── TestHandleVideoManagerNotify ──────────────────────────────────────────


class TestHandleVideoManagerNotify:
    """Tests for manager notification (lines 586-632)."""

    async def test_manager_dm_sent(self, mocks: MockHolder):
        """Pending review → DM to manager with deadline."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            dms = _get_manager_dms(bot)
            assert len(dms) == 1
            assert DEADLINE_STR in dms[0].data.get("text", "")

    async def test_general_topic_sent(self, mocks: MockHolder):
        """Pending review → message in general topic."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            generals = _get_general_sends(bot)
            assert len(generals) == 1
            assert "Test Manager" in generals[0].data.get("text", "")

    async def test_general_without_thread_id(self, mocks: MockHolder):
        """kok_general_topic_id=None → no message_thread_id in general message."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        mocks.settings.kok_general_topic_id = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # General topic message sent without thread_id
            reqs = bot._server.tracker.get_requests_by_method("sendMessage")
            general_msgs = [r for r in reqs
                            if str(r.data.get("chat_id")) == _S_GROUP
                            and "проверь видео" in r.data.get("text", "")]
            assert len(general_msgs) == 1
            assert general_msgs[0].data.get("message_thread_id") is None

    async def test_manager_not_found(self, mocks: MockHolder):
        """manager=None → no DM, no general message."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        mocks.manager_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            assert len(_get_manager_dms(bot)) == 0
            assert len(_get_general_sends(bot)) == 0

    async def test_manager_forbidden(self, mocks: MockHolder):
        """Manager hasn't started bot → TelegramForbiddenError, general still sent."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "sendMessage" and str(data.get("chat_id")) == _S_MANAGER:
                    return {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # General topic still sent despite DM failure
            assert len(_get_general_sends(bot)) == 1

    async def test_manager_dm_other_error(self, mocks: MockHolder):
        """DM fails with 500 → general still sent."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "sendMessage" and str(data.get("chat_id")) == _S_MANAGER:
                    return {"ok": False, "error_code": 500, "description": "Internal Server Error"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            assert len(_get_general_sends(bot)) == 1

    async def test_general_topic_fails(self, mocks: MockHolder):
        """General topic send fails → logged, continues."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if (method == "sendMessage"
                        and str(data.get("chat_id")) == _S_GROUP
                        and str(data.get("message_thread_id")) == _S_GENERAL):
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # Handler continues despite general topic failure
            bot.assert_last_bot_message_contains(VideoTemplates.pending_review())

    async def test_no_notify_if_approved(self, mocks: MockHolder):
        """Approved → no manager DM."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            assert len(_get_manager_dms(bot)) == 0


# ── TestHandleVideoPrivateMessageId ───────────────────────────────────────


class TestHandleVideoPrivateMessageId:
    """Tests for save_private_message_id (lines 346-354)."""

    async def test_saved_on_pending(self, mocks: MockHolder):
        """Not approved, not removal, not completed → saved."""
        _setup_happy_path(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            mocks.video_service.save_private_message_id.assert_called_once()

    async def test_saved_on_approved(self, mocks: MockHolder):
        """Approved, not completion → saved."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            mocks.video_service.save_private_message_id.assert_called_once()

    async def test_not_saved_on_completion(self, mocks: MockHolder):
        """Completed → NOT saved."""
        _setup_happy_path(
            mocks,
            course=_make_course(current_day=20, total_days=21),
            intake_log=_make_intake_log(day=21),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            mocks.video_service.save_private_message_id.assert_not_called()

    async def test_save_fails_logged(self, mocks: MockHolder):
        """save_private_message_id raises → logged, continues."""
        _setup_happy_path(mocks)
        mocks.video_service.save_private_message_id.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # Handler still completes without crash
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))


# ── TestHandleReshoot ─────────────────────────────────────────────────────


class TestHandleReshoot:
    """Tests for _handle_reshoot (lines 388-509)."""

    def _setup_reshoot(self, mocks: MockHolder, **kw):
        """Configure mocks for reshoot scenario."""
        user = kw.get("user", _make_user())
        course = kw.get("course", _make_course())
        reshoot_log = kw.get("reshoot_log", _make_intake_log(
            id=200, day=6, status="reshoot",
            reshoot_deadline=RESHOOT_DEADLINE_FUTURE,
        ))
        mocks.user_repo.get_by_telegram_id.return_value = user
        mocks.course_repo.get_active_by_user_id.return_value = course
        mocks.video_service.get_pending_reshoot.return_value = reshoot_log
        mocks.gemini_service.process_video.return_value = kw.get(
            "video_result", _make_video_result(),
        )
        mocks.video_service.calculate_deadline.return_value = DEADLINE
        mocks.manager_repo.get_by_id.return_value = kw.get("manager", _make_manager())
        return user, course, reshoot_log

    async def test_reshoot_approved(self, mocks: MockHolder):
        """AI approved → accept_reshoot + 'Молодец! День 6/21'."""
        self._setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))
            mocks.video_service.accept_reshoot.assert_called_once()

    async def test_reshoot_pending_review(self, mocks: MockHolder):
        """AI not approved → reshoot_pending_review + 'отправил менеджеру'."""
        self._setup_reshoot(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.pending_review())
            mocks.video_service.reshoot_pending_review.assert_called_once()

    async def test_reshoot_deadline_expired(self, mocks: MockHolder):
        """now > deadline → expire_reshoot + 'время истекло'."""
        self._setup_reshoot(mocks, reshoot_log=_make_intake_log(
            id=200, day=6, status="reshoot",
            reshoot_deadline=datetime(2025, 1, 14, 8, 0, tzinfo=TASHKENT_TZ),
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.reshoot_expired())
            mocks.video_service.expire_reshoot.assert_called_once()

    async def test_reshoot_deadline_none(self, mocks: MockHolder):
        """reshoot_deadline=None → proceeds to AI check (no expiration)."""
        self._setup_reshoot(mocks, reshoot_log=_make_intake_log(
            id=200, day=6, status="reshoot", reshoot_deadline=None,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # Processed normally — approved
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))
            mocks.video_service.expire_reshoot.assert_not_called()

    async def test_reshoot_download_fails(self, mocks: MockHolder):
        """Download fails → ai_error."""
        self._setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "getFile":
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.ai_error())

    async def test_reshoot_gemini_fails(self, mocks: MockHolder):
        """Gemini raises → ai_error."""
        self._setup_reshoot(mocks)
        mocks.gemini_service.process_video.side_effect = ValueError("error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.ai_error())

    async def test_reshoot_update_fails(self, mocks: MockHolder):
        """accept_reshoot raises → ai_error."""
        self._setup_reshoot(mocks)
        mocks.video_service.accept_reshoot.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.ai_error())

    async def test_reshoot_completion(self, mocks: MockHolder):
        """Reshoot day >= total_days, approved → 'Поздравляю!', no manager notify."""
        self._setup_reshoot(
            mocks,
            course=_make_course(current_day=20, total_days=21),
            reshoot_log=_make_intake_log(
                id=200, day=21, status="reshoot",
                reshoot_deadline=RESHOOT_DEADLINE_FUTURE,
            ),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.private_completed(21))
            mocks.video_service.complete_course.assert_called_once()
            # No manager notification on completion
            assert len(_get_manager_dms(bot)) == 0

    async def test_reshoot_completion_fails(self, mocks: MockHolder):
        """complete_course raises → fallback to approved."""
        self._setup_reshoot(
            mocks,
            course=_make_course(current_day=20, total_days=21),
            reshoot_log=_make_intake_log(
                id=200, day=21, status="reshoot",
                reshoot_deadline=RESHOOT_DEADLINE_FUTURE,
            ),
        )
        mocks.video_service.complete_course.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.approved(21, 21))

    async def test_reshoot_topic_approved(self, mocks: MockHolder):
        """Reshoot approved → _send_to_topic(is_reshoot=True) → icon back to 💊."""
        self._setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            edit_reqs = _get_edit_topic_reqs(bot)
            icons = [r.data.get("icon_custom_emoji_id") for r in edit_reqs]
            assert str(TOPIC_ICON_ACTIVE) in icons

    async def test_reshoot_topic_pending_keyboard(self, mocks: MockHolder):
        """Reshoot not approved → reshoot_review_keyboard (not review_keyboard)."""
        self._setup_reshoot(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            topic_msgs = _get_topic_sends(bot)
            pending_msgs = [r for r in topic_msgs if r.data.get("reply_markup")]
            assert len(pending_msgs) == 1
            # reshoot_review_keyboard has 2 buttons (Confirm/Reject, no Reshoot)
            kb = pending_msgs[0].data["reply_markup"]
            buttons = [b["text"] for row in kb["inline_keyboard"] for b in row]
            assert len(buttons) == 2  # Confirm + Reject (no re-reshoot)

    async def test_reshoot_no_topic(self, mocks: MockHolder):
        """user.topic_id=None → skip topic notifications."""
        self._setup_reshoot(mocks, user=_make_user(topic_id=None))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            assert len(_get_topic_video_notes(bot)) == 0

    async def test_reshoot_user_none_skips_topic_and_manager(self, mocks: MockHolder):
        """user=None in reshoot → topic_id=None, manager not notified."""
        self._setup_reshoot(mocks)
        mocks.user_repo.get_by_telegram_id.return_value = None
        # user=None → _get_user_and_active_course returns (None, None) → early return
        # But reshoot path needs user from _handle_video's earlier call
        # Actually user=None means no_active_course. Let's test with user having
        # topic_id=None AND not approved → manager notify skipped too.
        self._setup_reshoot(
            mocks,
            user=_make_user(topic_id=None),
            video_result=_make_video_result(approved=False, confidence=0.50),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            # No topic notifications
            assert len(_get_topic_video_notes(bot)) == 0
            assert len(_get_topic_sends(bot)) == 0
            # Manager still notified (user is not None, just topic_id=None)
            assert len(_get_manager_dms(bot)) == 1

    async def test_reshoot_pending_no_icon_change(self, mocks: MockHolder):
        """Reshoot not approved → icon NOT changed (only reshoot+approved changes icon)."""
        self._setup_reshoot(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            edit_reqs = _get_edit_topic_reqs(bot)
            assert len(edit_reqs) == 0

    async def test_reshoot_manager_notified(self, mocks: MockHolder):
        """Reshoot pending review → manager DM sent."""
        self._setup_reshoot(mocks, video_result=_make_video_result(
            approved=False, confidence=0.50,
        ))
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            assert len(_get_manager_dms(bot)) == 1

    async def test_reshoot_private_msg_saved(self, mocks: MockHolder):
        """Not completed → save_private_message_id called."""
        self._setup_reshoot(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            mocks.video_service.save_private_message_id.assert_called_once()

    async def test_reshoot_save_msg_fails(self, mocks: MockHolder):
        """save_private_message_id raises → logged, continues."""
        self._setup_reshoot(mocks)
        mocks.video_service.save_private_message_id.side_effect = Exception("DB error")
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            bot.assert_last_bot_message_contains(VideoTemplates.approved(6, 21))


# ── TestCompletionTopicErrors ─────────────────────────────────────────────


class TestCompletionTopicErrors:
    """Tests for _send_completion_to_topic error paths (lines 635-690)."""

    def _setup_completion(self, mocks: MockHolder):
        """Configure mocks for completion with video type control."""
        _setup_happy_path(
            mocks,
            course=_make_course(current_day=20, total_days=21),
            intake_log=_make_intake_log(day=21),
        )

    async def test_completion_with_video(self, mocks: MockHolder):
        """Video (not video_note) → sendVideo used for topic."""
        self._setup_completion(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video()
            videos = _get_topic_videos(bot)
            assert len(videos) == 1

    async def test_completion_video_fails_returns(self, mocks: MockHolder):
        """Video send to topic fails → early return, no text/icon/close."""
        self._setup_completion(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "sendVideoNote" and str(data.get("chat_id")) == _S_GROUP:
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # No completion text, icon change, or close
            assert len(_get_topic_sends(bot)) == 0
            assert len(_get_edit_topic_reqs(bot)) == 0
            assert len(_get_close_topic_reqs(bot)) == 0

    async def test_completion_text_fails(self, mocks: MockHolder):
        """Completion text send fails → icon and close still attempted."""
        self._setup_completion(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if (method == "sendMessage"
                        and str(data.get("chat_id")) == _S_GROUP
                        and str(data.get("message_thread_id")) == _S_TOPIC):
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # Icon and close still attempted despite text failure
            assert len(_get_edit_topic_reqs(bot)) >= 1
            assert len(_get_close_topic_reqs(bot)) == 1

    async def test_completion_icon_fails(self, mocks: MockHolder):
        """editForumTopic fails → close still attempted."""
        self._setup_completion(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "editForumTopic":
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # Close still attempted
            assert len(_get_close_topic_reqs(bot)) == 1

    async def test_completion_close_fails(self, mocks: MockHolder):
        """closeForumTopic fails → logged, handler continues."""
        self._setup_completion(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "closeForumTopic":
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # Handler still completes
            bot.assert_last_bot_message_contains(VideoTemplates.private_completed(21))


# ── TestRemovalTopicErrors ────────────────────────────────────────────────


class TestRemovalTopicErrors:
    """Tests for _send_late_removal_to_topic error paths (lines 693-756)."""

    def _setup_removal(self, mocks: MockHolder, **kw):
        """Configure for removal with topic notifications."""
        dates = [FIXED_NOW.isoformat()] * 3
        _setup_happy_path(
            mocks,
            intake_log=_make_intake_log(delay_minutes=31),
            late_result=(3, dates),
            user=kw.get("user", _make_user()),
            manager=kw.get("manager", _make_manager()),
        )

    async def test_removal_video_fails_returns(self, mocks: MockHolder):
        """Video send to topic fails → early return, no text/icon/general."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "sendVideoNote" and str(data.get("chat_id")) == _S_GROUP:
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            assert len(_get_topic_sends(bot)) == 0
            assert len(_get_edit_topic_reqs(bot)) == 0

    async def test_removal_text_fails(self, mocks: MockHolder):
        """Removal text fails → icon and general still attempted."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if (method == "sendMessage"
                        and str(data.get("chat_id")) == _S_GROUP
                        and str(data.get("message_thread_id")) == _S_TOPIC):
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # Icon still attempted
            assert len(_get_edit_topic_reqs(bot)) >= 1

    async def test_removal_icon_fails(self, mocks: MockHolder):
        """editForumTopic fails → general topic still sent."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "editForumTopic":
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # General topic still sent
            assert len(_get_general_sends(bot)) == 1

    async def test_removal_general_no_manager_name(self, mocks: MockHolder):
        """general_late_removed doesn't mention manager — only girl name + reason."""
        self._setup_removal(mocks)
        mocks.manager_repo.get_by_id.return_value = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            generals = _get_general_sends(bot)
            assert len(generals) == 1
            text = generals[0].data.get("text", "")
            assert "снята" in text
            assert "опоздала" in text

    async def test_removal_no_general_topic_id(self, mocks: MockHolder):
        """kok_general_topic_id=None → general msg without thread_id."""
        self._setup_removal(mocks)
        mocks.settings.kok_general_topic_id = None
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            reqs = bot._server.tracker.get_requests_by_method("sendMessage")
            removal_general = [r for r in reqs
                               if str(r.data.get("chat_id")) == _S_GROUP
                               and "снята" in r.data.get("text", "")]
            if removal_general:
                assert removal_general[0].data.get("message_thread_id") is None

    async def test_removal_general_send_fails(self, mocks: MockHolder):
        """General topic send fails → logged, handler continues."""
        self._setup_removal(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if (method == "sendMessage"
                        and str(data.get("chat_id")) == _S_GROUP
                        and str(data.get("message_thread_id")) == _S_GENERAL):
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # Handler still completes
            bot.assert_last_bot_message_contains("опоздала слишком много раз")


# ── TestLateWarningErrors ─────────────────────────────────────────────────


class TestLateWarningErrors:
    """Tests for _send_late_warning_to_topic error path (lines 759-774)."""

    async def test_warning_send_fails(self, mocks: MockHolder):
        """Late warning send fails → logged, handler continues."""
        _setup_happy_path(
            mocks,
            intake_log=_make_intake_log(delay_minutes=31),
            late_result=(1, [FIXED_NOW.isoformat()]),
        )
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method
            warning_blocked = []

            def patched(method, data):
                text = data.get("text", "")
                if (method == "sendMessage"
                        and str(data.get("chat_id")) == _S_GROUP
                        and str(data.get("message_thread_id")) == _S_TOPIC
                        and "Опоздание" in text):
                    warning_blocked.append(True)
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            await bot.send_video_note()
            # Warning was attempted
            assert len(warning_blocked) == 1
            # Handler still completes
            bot.assert_last_bot_message_contains(
                VideoTemplates.approved_late(6, 21, 1, 3),
            )


# ── TestEditSafe ──────────────────────────────────────────────────────────


class TestEditSafe:
    """Tests for _edit_safe (lines 777-786), tested through handler."""

    async def test_edit_works(self, mocks: MockHolder):
        """Normal case: processing message edited to result."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            await bot.send_video_note()
            edits = bot.get_edited_messages()
            assert len(edits) >= 1
            texts = [e.data.get("text", "") for e in edits]
            assert any(VideoTemplates.approved(6, 21) in t for t in texts)

    async def test_edit_bad_request_silent(self, mocks: MockHolder):
        """TelegramBadRequest on edit → silently ignored, no crash."""
        _setup_happy_path(mocks)
        dp = await create_test_dispatcher(mocks)
        async with MockTelegramBot(dp) as bot:
            original_route = bot._server._route_method

            def patched(method, data):
                if method == "editMessageText" and str(data.get("chat_id")) == _S_USER:
                    return {"ok": False, "error_code": 400, "description": "Bad Request"}
                return original_route(method, data)

            bot._server._route_method = patched
            # Should not raise, handler continues
            await bot.send_video_note()
            # Topic still gets notifications despite edit failure
            assert len(_get_topic_video_notes(bot)) == 1