"""Tests for CommandsMessagesRepository — real database, all 6 methods.

Key business logic:
- bot_type isolation: multiple bots share one table, each sees only its own
- is_menu flag: menu messages are tracked separately from regular commands
- delete_by_ids: early return on empty list (no bot_type filter — uses PK)
- delete_by_message_id: HAS bot_type filter (unlike delete_by_ids)
"""
import pytest
from supabase import AsyncClient

from repositories.commands_messages_repository import CommandsMessagesRepository

_BOT_TYPE = "kok"
_OTHER_BOT = "other_bot"


@pytest.fixture
def other_repo(supabase: AsyncClient) -> CommandsMessagesRepository:
    """Second repository with different bot_type for isolation tests."""
    return CommandsMessagesRepository(supabase, bot_type=_OTHER_BOT)


async def _insert(supabase: AsyncClient, message_id: int, bot_type: str = _BOT_TYPE, is_menu: bool = False) -> int:
    """Insert a commands_message directly, return its DB id."""
    response = await (
        supabase.table("commands_messages")
        .insert({"message_id": message_id, "bot_type": bot_type, "is_menu": is_menu})
        .execute()
    )
    return response.data[0]["id"]


# =============================================================================
# ADD MESSAGE
# =============================================================================


class TestAddMessage:
    async def test_adds_regular_message(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        await commands_messages_repository.add_message(1001)

        response = await (
            supabase.table("commands_messages")
            .select("message_id, bot_type, is_menu")
            .eq("message_id", 1001)
            .execute()
        )

        assert len(response.data) == 1
        row = response.data[0]
        assert row["message_id"] == 1001
        assert row["bot_type"] == _BOT_TYPE
        assert row["is_menu"] is False

    async def test_adds_menu_message(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        await commands_messages_repository.add_message(2001, is_menu=True)

        response = await (
            supabase.table("commands_messages")
            .select("is_menu")
            .eq("message_id", 2001)
            .execute()
        )

        assert response.data[0]["is_menu"] is True

    async def test_duplicate_message_id_raises_error(
        self, commands_messages_repository: CommandsMessagesRepository,
    ):
        """UNIQUE constraint на message_id — повторный вызов с тем же ID падает.
        Caller должен гарантировать уникальность.
        """
        from postgrest.exceptions import APIError

        await commands_messages_repository.add_message(3001)

        with pytest.raises(APIError, match="unique"):
            await commands_messages_repository.add_message(3001)


# =============================================================================
# GET NON-MENU MESSAGES
# =============================================================================


class TestGetNonMenuMessages:
    async def test_returns_non_menu_only(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        """Создаём menu + non-menu → возвращаются только non-menu."""
        await _insert(supabase, message_id=100, is_menu=False)
        await _insert(supabase, message_id=200, is_menu=True)

        messages = await commands_messages_repository.get_non_menu_messages()

        assert len(messages) == 1
        assert messages[0].message_id == 100
        assert messages[0].is_menu is False

    async def test_returns_multiple(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        """Все non-menu возвращаются (нет скрытого limit)."""
        await _insert(supabase, message_id=101)
        await _insert(supabase, message_id=102)
        await _insert(supabase, message_id=103)

        messages = await commands_messages_repository.get_non_menu_messages()

        assert len(messages) == 3
        ids = {m.message_id for m in messages}
        assert ids == {101, 102, 103}

    async def test_empty_when_no_messages(
        self, commands_messages_repository: CommandsMessagesRepository,
    ):
        messages = await commands_messages_repository.get_non_menu_messages()
        assert messages == []

    async def test_bot_type_isolation(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        """Сообщения другого бота не видны."""
        await _insert(supabase, message_id=100, bot_type=_BOT_TYPE)
        await _insert(supabase, message_id=200, bot_type=_OTHER_BOT)

        messages = await commands_messages_repository.get_non_menu_messages()

        assert len(messages) == 1
        assert messages[0].message_id == 100


# =============================================================================
# GET MENU MESSAGE
# =============================================================================


class TestGetMenuMessage:
    async def test_returns_menu_message(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        await _insert(supabase, message_id=500, is_menu=True)

        menu = await commands_messages_repository.get_menu_message()

        assert menu is not None
        assert menu.message_id == 500
        assert menu.is_menu is True

    async def test_none_when_no_menu(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        """Non-menu сообщения есть, но меню нет → None."""
        await _insert(supabase, message_id=100, is_menu=False)

        result = await commands_messages_repository.get_menu_message()
        assert result is None

    async def test_returns_one_when_multiple_menus(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        """limit(1) — если случайно 2 меню, не падает."""
        await _insert(supabase, message_id=500, is_menu=True)
        await _insert(supabase, message_id=501, is_menu=True)

        menu = await commands_messages_repository.get_menu_message()

        assert menu is not None
        assert menu.message_id in (500, 501)

    async def test_bot_type_isolation(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        """Чужое меню не видно."""
        await _insert(supabase, message_id=500, bot_type=_OTHER_BOT, is_menu=True)

        result = await commands_messages_repository.get_menu_message()
        assert result is None


# =============================================================================
# DELETE BY IDS
# =============================================================================


class TestDeleteByIds:
    async def test_deletes_specified_ids(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        id_a = await _insert(supabase, message_id=100)
        id_b = await _insert(supabase, message_id=200)
        id_keep = await _insert(supabase, message_id=300)

        await commands_messages_repository.delete_by_ids([id_a, id_b])

        remaining = await commands_messages_repository.get_non_menu_messages()
        assert len(remaining) == 1
        assert remaining[0].id == id_keep

    async def test_empty_list_does_nothing(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        """if not ids: return — ранний выход, ничего не удаляется."""
        await _insert(supabase, message_id=100)

        await commands_messages_repository.delete_by_ids([])

        messages = await commands_messages_repository.get_non_menu_messages()
        assert len(messages) == 1

    async def test_nonexistent_ids_no_error(
        self, commands_messages_repository: CommandsMessagesRepository,
    ):
        """Несуществующие ID не вызывают ошибку."""
        await commands_messages_repository.delete_by_ids([999999, 888888])


# =============================================================================
# DELETE BY MESSAGE ID
# =============================================================================


class TestDeleteByMessageId:
    async def test_deletes_matching(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        await _insert(supabase, message_id=100)
        await _insert(supabase, message_id=200)

        await commands_messages_repository.delete_by_message_id(100)

        remaining = await commands_messages_repository.get_non_menu_messages()
        assert len(remaining) == 1
        assert remaining[0].message_id == 200

    async def test_bot_type_filter_prevents_foreign_delete(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
        other_repo: CommandsMessagesRepository,
    ):
        """bot_type фильтр: delete_by_message_id НЕ удаляет чужое сообщение.
        message_id разные (UNIQUE constraint), но проверяем что фильтр работает.
        """
        await _insert(supabase, message_id=100, bot_type=_BOT_TYPE)
        await _insert(supabase, message_id=200, bot_type=_OTHER_BOT)

        # "kok" бот пытается удалить message_id=200 (принадлежит other_bot)
        await commands_messages_repository.delete_by_message_id(200)

        # Чужое НЕ удалено (bot_type фильтр защитил)
        other = await other_repo.get_non_menu_messages()
        assert len(other) == 1
        assert other[0].message_id == 200

        # Своё на месте
        own = await commands_messages_repository.get_non_menu_messages()
        assert len(own) == 1

    async def test_nonexistent_no_error(
        self, commands_messages_repository: CommandsMessagesRepository,
    ):
        """Несуществующий message_id → тишина."""
        await commands_messages_repository.delete_by_message_id(999999)


# =============================================================================
# DELETE MENU MESSAGE
# =============================================================================


class TestDeleteMenuMessage:
    async def test_deletes_menu(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        await _insert(supabase, message_id=500, is_menu=True)

        await commands_messages_repository.delete_menu_message()

        result = await commands_messages_repository.get_menu_message()
        assert result is None

    async def test_bot_type_isolation(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
        other_repo: CommandsMessagesRepository,
    ):
        """Чужое меню не трогает."""
        await _insert(supabase, message_id=500, bot_type=_BOT_TYPE, is_menu=True)
        await _insert(supabase, message_id=600, bot_type=_OTHER_BOT, is_menu=True)

        await commands_messages_repository.delete_menu_message()

        # Своё удалено
        own = await commands_messages_repository.get_menu_message()
        assert own is None

        # Чужое осталось
        other = await other_repo.get_menu_message()
        assert other is not None
        assert other.message_id == 600

    async def test_does_not_delete_non_menu(
        self, supabase: AsyncClient,
        commands_messages_repository: CommandsMessagesRepository,
    ):
        """Удаляет только is_menu=True, non-menu остаются."""
        await _insert(supabase, message_id=100, is_menu=False)
        await _insert(supabase, message_id=500, is_menu=True)

        await commands_messages_repository.delete_menu_message()

        non_menu = await commands_messages_repository.get_non_menu_messages()
        assert len(non_menu) == 1
        assert non_menu[0].message_id == 100