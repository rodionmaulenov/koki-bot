"""Tests for CommandsMessagesService — 10 tests."""
from unittest.mock import AsyncMock

from topic_access.service import CommandsMessagesService

from .conftest import CHAT_ID, make_cmd_msg, make_telegram_bad_request, make_telegram_forbidden


def _svc(
    repo: AsyncMock | None = None,
    bot: AsyncMock | None = None,
    chat_id: int = CHAT_ID,
) -> tuple[CommandsMessagesService, AsyncMock, AsyncMock]:
    """Create service with mocks. Returns (service, bot, repo)."""
    if repo is None:
        repo = AsyncMock()
    if bot is None:
        bot = AsyncMock()
    svc = CommandsMessagesService(bot=bot, repository=repo, chat_id=chat_id)
    return svc, bot, repo


# ── Empty case ──────────────────────────────────────────────────────────────


async def test_no_messages_returns_zero():
    """No messages → returns 0, no Telegram calls."""
    repo = AsyncMock()
    repo.get_non_menu_messages.return_value = []
    svc, bot, _ = _svc(repo=repo)

    result = await svc.clear_messages()

    assert result == 0
    bot.delete_messages.assert_not_called()
    repo.delete_by_ids.assert_not_called()


# ── Happy path ──────────────────────────────────────────────────────────────


async def test_deletes_from_telegram_and_db():
    """Deletes messages from Telegram (batch) and DB."""
    msgs = [make_cmd_msg(db_id=1, message_id=100), make_cmd_msg(db_id=2, message_id=101)]
    repo = AsyncMock()
    repo.get_non_menu_messages.return_value = msgs
    svc, bot, _ = _svc(repo=repo)

    result = await svc.clear_messages()

    assert result == 2
    bot.delete_messages.assert_called_once_with(
        chat_id=CHAT_ID, message_ids=[100, 101],
    )
    repo.delete_by_ids.assert_called_once_with([1, 2])


async def test_returns_correct_count():
    """Returns count of successfully handled messages."""
    msgs = [make_cmd_msg(db_id=i, message_id=i + 100) for i in range(5)]
    repo = AsyncMock()
    repo.get_non_menu_messages.return_value = msgs
    svc, _, _ = _svc(repo=repo)

    result = await svc.clear_messages()

    assert result == 5


async def test_uses_correct_chat_id():
    """Uses chat_id from constructor in delete_messages call."""
    custom_chat_id = -1009999999
    msgs = [make_cmd_msg(db_id=1, message_id=100)]
    repo = AsyncMock()
    repo.get_non_menu_messages.return_value = msgs
    svc, bot, _ = _svc(repo=repo, chat_id=custom_chat_id)

    await svc.clear_messages()

    bot.delete_messages.assert_called_once_with(
        chat_id=custom_chat_id, message_ids=[100],
    )


# ── Error handling ──────────────────────────────────────────────────────────


async def test_telegram_bad_request_still_cleans_db():
    """TelegramBadRequest → messages still removed from DB.

    BadRequest means messages don't exist in Telegram anymore.
    """
    msgs = [make_cmd_msg(db_id=1, message_id=100)]
    repo = AsyncMock()
    repo.get_non_menu_messages.return_value = msgs
    bot = AsyncMock()
    bot.delete_messages.side_effect = make_telegram_bad_request("not found")
    svc, _, _ = _svc(repo=repo, bot=bot)

    result = await svc.clear_messages()

    assert result == 1
    repo.delete_by_ids.assert_called_once_with([1])


async def test_telegram_forbidden_does_not_clean_db():
    """TelegramForbiddenError → messages NOT removed from DB.

    Forbidden means bot lost permission. Messages may still exist.
    Keep in DB for retry when permission restored.
    """
    msgs = [make_cmd_msg(db_id=1, message_id=100)]
    repo = AsyncMock()
    repo.get_non_menu_messages.return_value = msgs
    bot = AsyncMock()
    bot.delete_messages.side_effect = make_telegram_forbidden("kicked")
    svc, _, _ = _svc(repo=repo, bot=bot)

    result = await svc.clear_messages()

    assert result == 0
    repo.delete_by_ids.assert_not_called()


# ── Batching ────────────────────────────────────────────────────────────────


async def test_batch_size_100():
    """150 messages → 2 batches (100 + 50)."""
    msgs = [make_cmd_msg(db_id=i, message_id=i + 1000) for i in range(150)]
    repo = AsyncMock()
    repo.get_non_menu_messages.return_value = msgs
    svc, bot, _ = _svc(repo=repo)

    result = await svc.clear_messages()

    assert result == 150
    assert bot.delete_messages.call_count == 2

    # First batch: 100 messages
    first_call = bot.delete_messages.call_args_list[0]
    assert len(first_call.kwargs["message_ids"]) == 100

    # Second batch: 50 messages
    second_call = bot.delete_messages.call_args_list[1]
    assert len(second_call.kwargs["message_ids"]) == 50


async def test_exactly_100_messages_one_batch():
    """Exactly 100 messages → 1 batch, not 2."""
    msgs = [make_cmd_msg(db_id=i, message_id=i + 1000) for i in range(100)]
    repo = AsyncMock()
    repo.get_non_menu_messages.return_value = msgs
    svc, bot, _ = _svc(repo=repo)

    result = await svc.clear_messages()

    assert result == 100
    assert bot.delete_messages.call_count == 1


async def test_partial_batch_forbidden():
    """First batch OK, second Forbidden → only first batch cleaned from DB."""
    msgs = [make_cmd_msg(db_id=i, message_id=i + 1000) for i in range(150)]
    repo = AsyncMock()
    repo.get_non_menu_messages.return_value = msgs
    bot = AsyncMock()
    bot.delete_messages.side_effect = [None, make_telegram_forbidden("kicked")]
    svc, _, _ = _svc(repo=repo, bot=bot)

    result = await svc.clear_messages()

    # Only first 100 deleted
    assert result == 100
    repo.delete_by_ids.assert_called_once()
    deleted_ids = repo.delete_by_ids.call_args[0][0]
    assert len(deleted_ids) == 100
