"""Tests for handlers/menu.py.

Tests on_clear (callback), delete_service_messages, ensure_menu.
Uses MockTelegramBot with Dishka integration for real Telegram API simulation.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    Chat,
    ForumTopicClosed,
    ForumTopicCreated,
    ForumTopicEdited,
    ForumTopicReopened,
    Message,
    Update,
    User,
)

from callbacks.menu import MenuAction, MenuCallback
from handlers.menu import ensure_menu
from keyboards.menu import main_menu_keyboard
from templates import MenuTemplates
from tests.handlers.conftest import COMMANDS_THREAD_ID, KOK_GROUP_ID, MockHolder, create_test_dispatcher
from tests.mock_server import MockTelegramBot
from topic_access.message_middleware import ADD_ACTIVE_KEY_PREFIX

BOT_ID = 1234567890


def _inject_menu_message(bot: MockTelegramBot) -> int:
    """Inject a fake bot menu message into chat_state. Returns message_id."""
    msg = bot.chat_state.add_message(
        chat_id=bot.chat_id,
        from_user_id=BOT_ID,
        is_bot=True,
        text=MenuTemplates.main_menu(),
        reply_markup={
            "inline_keyboard": [
                [{"text": "➕ Добавить", "callback_data": "menu:add"}],
                [{"text": "🗑 Очистить", "callback_data": "menu:clear"}],
            ]
        },
        message_thread_id=COMMANDS_THREAD_ID,
    )
    return msg.message_id


def _make_service_message_update(
    chat_id: int,
    message_thread_id: int,
    *,
    forum_topic_edited: ForumTopicEdited | None = None,
    forum_topic_created: ForumTopicCreated | None = None,
    forum_topic_closed: ForumTopicClosed | None = None,
    forum_topic_reopened: ForumTopicReopened | None = None,
) -> Update:
    """Create Update with forum service message."""
    return Update(
        update_id=999,
        message=Message(
            message_id=555,
            date=datetime.now(),
            chat=Chat(id=chat_id, type="supergroup", title="Test Group"),
            from_user=User(id=123, is_bot=False, first_name="Test"),
            message_thread_id=message_thread_id,
            forum_topic_edited=forum_topic_edited,
            forum_topic_created=forum_topic_created,
            forum_topic_closed=forum_topic_closed,
            forum_topic_reopened=forum_topic_reopened,
        ),
    )


# ── on_clear ─────────────────────────────────────────────────────────────────


class TestOnClear:
    """on_clear: manager clicks '🗑 Clear' button."""

    async def test_clear_calls_service(self, mocks: MockHolder):
        """Clicking Clear → CommandsMessagesService.clear_messages() called."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            _inject_menu_message(bot)

            callback_data = MenuCallback(action=MenuAction.CLEAR).pack()
            await bot.click_button(callback_data)

            mocks.commands_messages_service.clear_messages.assert_called_once()

    async def test_clear_answers_callback(self, mocks: MockHolder):
        """Clear → callback answered with 'Топик очищен'."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            _inject_menu_message(bot)

            callback_data = MenuCallback(action=MenuAction.CLEAR).pack()
            await bot.click_button(callback_data)

            answers = bot.get_callback_answers()
            assert len(answers) >= 1
            assert answers[-1].data.get("text") == MenuTemplates.topic_cleared()

    async def test_clear_deletes_redis_key(self, mocks: MockHolder):
        """Clear with thread_id → Redis ADD_ACTIVE key deleted."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            _inject_menu_message(bot)

            callback_data = MenuCallback(action=MenuAction.CLEAR).pack()
            await bot.click_button(callback_data)

            expected_key = f"{ADD_ACTIVE_KEY_PREFIX}:{COMMANDS_THREAD_ID}"
            mocks.redis.delete.assert_called_once_with(expected_key)

    async def test_clear_clears_fsm_state(self, mocks: MockHolder):
        """Clear → FSM state is reset to None."""
        dp = await create_test_dispatcher(mocks)
        user_id = 123456789

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
            user_id=user_id,
        ) as bot:
            # Pre-set FSM state to simulate active session
            key = StorageKey(
                bot_id=bot.bot.id,
                chat_id=KOK_GROUP_ID,
                user_id=user_id,
            )
            await dp.storage.set_state(key, "SomeState:step")
            await dp.storage.set_data(key, {"some_key": "some_value"})

            _inject_menu_message(bot)

            callback_data = MenuCallback(action=MenuAction.CLEAR).pack()
            await bot.click_button(callback_data)

            # FSM state should be cleared
            state_after = await dp.storage.get_state(key)
            data_after = await dp.storage.get_data(key)
            assert state_after is None
            assert data_after == {}

    async def test_clear_no_thread_id_skips_redis(self, mocks: MockHolder):
        """Clear without thread_id → Redis delete NOT called."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=None,
        ) as bot:
            # Inject menu message without thread_id
            bot.chat_state.add_message(
                chat_id=bot.chat_id,
                from_user_id=BOT_ID,
                is_bot=True,
                text="Menu",
                message_thread_id=None,
            )

            callback_data = MenuCallback(action=MenuAction.CLEAR).pack()
            await bot.click_button(callback_data)

            mocks.redis.delete.assert_not_called()

    async def test_clear_redis_error_suppressed(self, mocks: MockHolder):
        """Redis error during clear → suppressed, handler completes."""
        mocks.redis.delete.side_effect = Exception("Redis connection lost")
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            _inject_menu_message(bot)

            callback_data = MenuCallback(action=MenuAction.CLEAR).pack()
            await bot.click_button(callback_data)

            # Handler continues despite Redis error
            mocks.commands_messages_service.clear_messages.assert_called_once()
            answers = bot.get_callback_answers()
            assert len(answers) >= 1

    async def test_clear_callback_answer_text(self, mocks: MockHolder):
        """Clear → callback answer text is exactly 'Топик очищен'."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            _inject_menu_message(bot)

            callback_data = MenuCallback(action=MenuAction.CLEAR).pack()
            await bot.click_button(callback_data)

            answers = bot.get_callback_answers()
            assert answers[-1].data["text"] == "Топик очищен"


# ── delete_service_messages ──────────────────────────────────────────────────


class TestDeleteServiceMessages:
    """delete_service_messages: auto-delete forum service messages."""

    async def test_deletes_forum_topic_edited(self, mocks: MockHolder):
        """forum_topic_edited message → deleted."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            update = _make_service_message_update(
                KOK_GROUP_ID,
                COMMANDS_THREAD_ID,
                forum_topic_edited=ForumTopicEdited(),
            )

            await dp.feed_update(bot.bot, update)

            deleted = bot.get_deleted_messages()
            assert len(deleted) == 1
            assert int(deleted[0].data["message_id"]) == 555

    async def test_deletes_forum_topic_created(self, mocks: MockHolder):
        """forum_topic_created message → deleted."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            update = _make_service_message_update(
                KOK_GROUP_ID,
                COMMANDS_THREAD_ID,
                forum_topic_created=ForumTopicCreated(
                    name="Test Topic",
                    icon_color=7322096,
                ),
            )

            await dp.feed_update(bot.bot, update)

            deleted = bot.get_deleted_messages()
            assert len(deleted) == 1

    async def test_deletes_forum_topic_closed(self, mocks: MockHolder):
        """forum_topic_closed message → deleted."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            update = _make_service_message_update(
                KOK_GROUP_ID,
                COMMANDS_THREAD_ID,
                forum_topic_closed=ForumTopicClosed(),
            )

            await dp.feed_update(bot.bot, update)

            deleted = bot.get_deleted_messages()
            assert len(deleted) == 1

    async def test_deletes_forum_topic_reopened(self, mocks: MockHolder):
        """forum_topic_reopened message → deleted."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            update = _make_service_message_update(
                KOK_GROUP_ID,
                COMMANDS_THREAD_ID,
                forum_topic_reopened=ForumTopicReopened(),
            )

            await dp.feed_update(bot.bot, update)

            deleted = bot.get_deleted_messages()
            assert len(deleted) == 1

    async def test_delete_fails_silently(self, mocks: MockHolder):
        """message.delete() raises TelegramBadRequest → no crash, warning logged."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            # Make mock server return error for deleteMessage
            original_route = bot._server._route_method

            def patched_route(method, data):
                if method == "deleteMessage":
                    return {
                        "ok": False,
                        "error_code": 400,
                        "description": "Bad Request: message can't be deleted for everyone",
                    }
                return original_route(method, data)

            bot._server._route_method = patched_route

            update = _make_service_message_update(
                KOK_GROUP_ID,
                COMMANDS_THREAD_ID,
                forum_topic_edited=ForumTopicEdited(),
            )

            # Should not raise — handler catches TelegramBadRequest
            await dp.feed_update(bot.bot, update)

    async def test_normal_message_not_deleted(self, mocks: MockHolder):
        """Regular text message → NOT deleted (no service filter match)."""
        dp = await create_test_dispatcher(mocks)

        async with MockTelegramBot(
            dp,
            chat_id=KOK_GROUP_ID,
            chat_type="supergroup",
            message_thread_id=COMMANDS_THREAD_ID,
        ) as bot:
            await bot.send_message("regular text message")

            deleted = bot.get_deleted_messages()
            assert len(deleted) == 0


# ── ensure_menu ──────────────────────────────────────────────────────────────


class TestEnsureMenu:
    """ensure_menu: edit existing or send new menu."""

    async def test_edits_existing_menu(self, mocks: MockHolder):
        """Existing menu in DB → edit message text."""
        existing = MagicMock()
        existing.message_id = 42
        mocks.commands_messages_repo.get_menu_message.return_value = existing

        await ensure_menu(
            mocks.tracked_bot, KOK_GROUP_ID, COMMANDS_THREAD_ID, mocks.commands_messages_repo,
        )

        mocks.tracked_bot.edit_message_text.assert_called_once()
        call_kwargs = mocks.tracked_bot.edit_message_text.call_args.kwargs
        assert call_kwargs["chat_id"] == KOK_GROUP_ID
        assert call_kwargs["message_id"] == 42
        assert call_kwargs["text"] == MenuTemplates.main_menu()
        assert call_kwargs["reply_markup"] == main_menu_keyboard()
        mocks.tracked_bot.send_menu_message.assert_not_called()

    async def test_sends_new_when_no_existing(self, mocks: MockHolder):
        """No menu in DB → send new menu."""
        mocks.commands_messages_repo.get_menu_message.return_value = None

        await ensure_menu(
            mocks.tracked_bot, KOK_GROUP_ID, COMMANDS_THREAD_ID, mocks.commands_messages_repo,
        )

        mocks.tracked_bot.send_menu_message.assert_called_once()
        call_kwargs = mocks.tracked_bot.send_menu_message.call_args.kwargs
        assert call_kwargs["chat_id"] == KOK_GROUP_ID
        assert call_kwargs["message_thread_id"] == COMMANDS_THREAD_ID
        assert call_kwargs["text"] == MenuTemplates.main_menu()
        assert call_kwargs["reply_markup"] == main_menu_keyboard()
        mocks.tracked_bot.edit_message_text.assert_not_called()

    async def test_not_modified_silently_returns(self, mocks: MockHolder):
        """Edit returns 'message is not modified' → no error, no new menu."""
        existing = MagicMock()
        existing.message_id = 42
        mocks.commands_messages_repo.get_menu_message.return_value = existing
        mocks.tracked_bot.edit_message_text.side_effect = TelegramBadRequest(
            method=MagicMock(), message="message is not modified",
        )

        await ensure_menu(
            mocks.tracked_bot, KOK_GROUP_ID, COMMANDS_THREAD_ID, mocks.commands_messages_repo,
        )

        mocks.tracked_bot.send_menu_message.assert_not_called()
        mocks.commands_messages_repo.delete_menu_message.assert_not_called()

    async def test_edit_fails_deletes_and_sends_new(self, mocks: MockHolder):
        """Edit fails (not 'not modified') → delete old from DB → send new."""
        existing = MagicMock()
        existing.message_id = 42
        mocks.commands_messages_repo.get_menu_message.return_value = existing
        mocks.tracked_bot.edit_message_text.side_effect = TelegramBadRequest(
            method=MagicMock(), message="message to edit not found",
        )

        await ensure_menu(
            mocks.tracked_bot, KOK_GROUP_ID, COMMANDS_THREAD_ID, mocks.commands_messages_repo,
        )

        mocks.commands_messages_repo.delete_menu_message.assert_called_once()
        mocks.tracked_bot.send_menu_message.assert_called_once()

    async def test_db_error_get_menu_sends_new(self, mocks: MockHolder):
        """DB error when getting menu → send new menu."""
        mocks.commands_messages_repo.get_menu_message.side_effect = Exception("DB error")

        await ensure_menu(
            mocks.tracked_bot, KOK_GROUP_ID, COMMANDS_THREAD_ID, mocks.commands_messages_repo,
        )

        mocks.tracked_bot.send_menu_message.assert_called_once()

    async def test_db_error_delete_still_sends_new(self, mocks: MockHolder):
        """DB error deleting old menu → still send new menu."""
        existing = MagicMock()
        existing.message_id = 42
        mocks.commands_messages_repo.get_menu_message.return_value = existing
        mocks.tracked_bot.edit_message_text.side_effect = TelegramBadRequest(
            method=MagicMock(), message="message to edit not found",
        )
        mocks.commands_messages_repo.delete_menu_message.side_effect = Exception("DB error")

        await ensure_menu(
            mocks.tracked_bot, KOK_GROUP_ID, COMMANDS_THREAD_ID, mocks.commands_messages_repo,
        )

        mocks.tracked_bot.send_menu_message.assert_called_once()

    async def test_edit_passes_parse_mode_html(self, mocks: MockHolder):
        """Edit uses parse_mode='HTML'."""
        existing = MagicMock()
        existing.message_id = 42
        mocks.commands_messages_repo.get_menu_message.return_value = existing

        await ensure_menu(
            mocks.tracked_bot, KOK_GROUP_ID, COMMANDS_THREAD_ID, mocks.commands_messages_repo,
        )

        call_kwargs = mocks.tracked_bot.edit_message_text.call_args.kwargs
        assert call_kwargs["parse_mode"] == "HTML"

    async def test_send_new_passes_parse_mode_html(self, mocks: MockHolder):
        """Send new menu uses parse_mode='HTML'."""
        mocks.commands_messages_repo.get_menu_message.return_value = None

        await ensure_menu(
            mocks.tracked_bot, KOK_GROUP_ID, COMMANDS_THREAD_ID, mocks.commands_messages_repo,
        )

        call_kwargs = mocks.tracked_bot.send_menu_message.call_args.kwargs
        assert call_kwargs["parse_mode"] == "HTML"