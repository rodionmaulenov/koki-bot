"""Tests for TrackedBot — 16 tests."""
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Bot
from aiogram.methods import (
    EditMessageCaption,
    EditMessageMedia,
    EditMessageReplyMarkup,
    EditMessageText,
    SendMessage,
)
from aiogram.types import InputMediaPhoto

from topic_access.tracked_bot import TrackedBot

from .conftest import CHAT_ID, THREAD_ID, make_bot_message

_SUPER_CALL = "aiogram.Bot.__call__"


def _bot(repo: AsyncMock | None = None) -> tuple[TrackedBot, AsyncMock]:
    """Create TrackedBot with mock repo. Returns (bot, repo)."""
    if repo is None:
        repo = AsyncMock()
    bot = TrackedBot(
        token="123:TEST",
        repository=repo,
        thread_id=THREAD_ID,
        chat_id=CHAT_ID,
    )
    return bot, repo


# ── __call__: tracking in target topic ──────────────────────────────────────


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_tracks_message_in_target(mock_super):
    """Message in correct chat + topic → tracked with is_menu=False."""
    mock_super.return_value = make_bot_message(
        chat_id=CHAT_ID, thread_id=THREAD_ID, message_id=500,
    )
    bot, repo = _bot()
    method = SendMessage(chat_id=CHAT_ID, text="test", message_thread_id=THREAD_ID)

    result = await bot(method)

    repo.add_message.assert_called_once_with(message_id=500, is_menu=False)
    assert result.message_id == 500


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_does_not_track_other_topic(mock_super):
    """Message in different thread → NOT tracked."""
    mock_super.return_value = make_bot_message(
        chat_id=CHAT_ID, thread_id=999, message_id=501,
    )
    bot, repo = _bot()
    method = SendMessage(chat_id=CHAT_ID, text="test", message_thread_id=999)

    await bot(method)

    repo.add_message.assert_not_called()


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_does_not_track_other_chat(mock_super):
    """Message in different chat → NOT tracked."""
    mock_super.return_value = make_bot_message(
        chat_id=-100999, thread_id=THREAD_ID, message_id=502,
    )
    bot, repo = _bot()
    method = SendMessage(chat_id=-100999, text="test")

    await bot(method)

    repo.add_message.assert_not_called()


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_message_thread_id_none_treated_as_zero(mock_super):
    """message_thread_id=None → treated as 0. If bot thread_id≠0, not tracked."""
    mock_super.return_value = make_bot_message(
        chat_id=CHAT_ID, thread_id=None, message_id=503,
    )
    bot, repo = _bot()  # thread_id=42
    method = SendMessage(chat_id=CHAT_ID, text="test")

    await bot(method)

    repo.add_message.assert_not_called()


# ── __call__: edit methods skipped ──────────────────────────────────────────


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_edit_text_skipped(mock_super):
    """EditMessageText → skip tracking."""
    mock_super.return_value = make_bot_message()
    bot, repo = _bot()
    method = EditMessageText(chat_id=CHAT_ID, message_id=1, text="edited")

    await bot(method)

    repo.add_message.assert_not_called()


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_edit_reply_markup_skipped(mock_super):
    """EditMessageReplyMarkup → skip tracking."""
    mock_super.return_value = make_bot_message()
    bot, repo = _bot()
    method = EditMessageReplyMarkup(chat_id=CHAT_ID, message_id=1)

    await bot(method)

    repo.add_message.assert_not_called()


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_edit_caption_skipped(mock_super):
    """EditMessageCaption → skip tracking."""
    mock_super.return_value = make_bot_message()
    bot, repo = _bot()
    method = EditMessageCaption(chat_id=CHAT_ID, message_id=1, caption="new")

    await bot(method)

    repo.add_message.assert_not_called()


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_edit_media_skipped(mock_super):
    """EditMessageMedia → skip tracking."""
    mock_super.return_value = make_bot_message()
    bot, repo = _bot()
    method = EditMessageMedia(
        chat_id=CHAT_ID, message_id=1,
        media=InputMediaPhoto(media="photo_id"),
    )

    await bot(method)

    repo.add_message.assert_not_called()


# ── __call__: non-Message results ───────────────────────────────────────────


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_non_message_result_not_tracked(mock_super):
    """Result is bool (e.g. delete_message) → not tracked."""
    mock_super.return_value = True
    bot, repo = _bot()
    method = SendMessage(chat_id=CHAT_ID, text="test")

    result = await bot(method)

    repo.add_message.assert_not_called()
    assert result is True


# ── send_menu_message ───────────────────────────────────────────────────────


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_send_menu_marks_is_menu(mock_super):
    """send_menu_message → tracked with is_menu=True."""
    mock_super.return_value = make_bot_message(
        chat_id=CHAT_ID, thread_id=THREAD_ID, message_id=600,
    )
    bot, repo = _bot()

    result = await bot.send_menu_message(
        chat_id=CHAT_ID, text="Menu", message_thread_id=THREAD_ID,
    )

    repo.add_message.assert_called_once_with(message_id=600, is_menu=True)
    assert result.message_id == 600


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_regular_message_not_menu(mock_super):
    """Regular send_message → is_menu=False."""
    mock_super.return_value = make_bot_message(
        chat_id=CHAT_ID, thread_id=THREAD_ID, message_id=601,
    )
    bot, repo = _bot()
    method = SendMessage(
        chat_id=CHAT_ID, text="Regular", message_thread_id=THREAD_ID,
    )

    await bot(method)

    repo.add_message.assert_called_once_with(message_id=601, is_menu=False)


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_menu_flag_resets_after_track(mock_super):
    """_menu_message_pending resets to False after tracking."""
    mock_super.return_value = make_bot_message(
        chat_id=CHAT_ID, thread_id=THREAD_ID, message_id=602,
    )
    bot, repo = _bot()

    await bot.send_menu_message(
        chat_id=CHAT_ID, text="Menu", message_thread_id=THREAD_ID,
    )

    assert bot._menu_message_pending is False

    # Next regular message should be is_menu=False
    mock_super.return_value = make_bot_message(
        chat_id=CHAT_ID, thread_id=THREAD_ID, message_id=603,
    )
    method = SendMessage(
        chat_id=CHAT_ID, text="Regular", message_thread_id=THREAD_ID,
    )
    await bot(method)

    repo.add_message.assert_any_call(message_id=603, is_menu=False)


@patch(_SUPER_CALL, new_callable=AsyncMock)
async def test_menu_flag_persists_after_api_error(mock_super):
    """BUG: if super().__call__ raises, _menu_message_pending stays True.

    Next regular send_message is incorrectly marked as menu.
    """
    mock_super.side_effect = RuntimeError("API error")
    bot, repo = _bot()

    try:
        await bot.send_menu_message(
            chat_id=CHAT_ID, text="Menu", message_thread_id=THREAD_ID,
        )
    except RuntimeError:
        pass

    # Flag is stuck at True
    assert bot._menu_message_pending is True

    # Next successful call: regular message gets is_menu=True (BUG!)
    mock_super.side_effect = None
    mock_super.return_value = make_bot_message(
        chat_id=CHAT_ID, thread_id=THREAD_ID, message_id=700,
    )
    method = SendMessage(
        chat_id=CHAT_ID, text="Regular", message_thread_id=THREAD_ID,
    )
    await bot(method)

    repo.add_message.assert_called_once_with(message_id=700, is_menu=True)


# ── untrack_message ─────────────────────────────────────────────────────────


async def test_untrack_deletes_from_repo():
    """untrack_message → calls delete_by_message_id."""
    bot, repo = _bot()

    await bot.untrack_message(123)

    repo.delete_by_message_id.assert_called_once_with(123)


async def test_untrack_handles_exception():
    """Exception in delete_by_message_id → logged, no crash."""
    repo = AsyncMock()
    repo.delete_by_message_id.side_effect = RuntimeError("DB error")
    bot, _ = _bot(repo=repo)

    await bot.untrack_message(123)  # should not raise

    repo.delete_by_message_id.assert_called_once_with(123)
