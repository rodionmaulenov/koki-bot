"""Tests for ManagerRepository — real database, all 3 methods.

Key edge case: NO is_active filter on get_by_id/get_by_telegram_id —
inactive managers are still returned. This is intentional: deactivated managers
must be findable for display on existing records.
"""
from supabase import AsyncClient

from repositories.manager_repository import ManagerRepository
from tests.conftest import create_test_manager


# =============================================================================
# GET BY ID
# =============================================================================


class TestGetById:
    async def test_returns_manager_with_all_fields(
        self, supabase: AsyncClient, manager_repository: ManagerRepository,
    ):
        created = await create_test_manager(supabase, telegram_id=111, name="Alice")

        manager = await manager_repository.get_by_id(created.id)

        assert manager is not None
        assert manager.id == created.id
        assert manager.telegram_id == 111
        assert manager.name == "Alice"
        assert manager.is_active is True
        assert manager.created_at is not None

    async def test_nonexistent_returns_none(
        self, manager_repository: ManagerRepository,
    ):
        result = await manager_repository.get_by_id(999999)
        assert result is None

    async def test_inactive_manager_still_found(
        self, supabase: AsyncClient, manager_repository: ManagerRepository,
    ):
        """is_active=False — менеджер всё равно возвращается.
        Если кто-то добавит .eq("is_active", True) — тест упадёт.
        """
        created = await create_test_manager(
            supabase, telegram_id=222, name="Inactive", is_active=False,
        )

        manager = await manager_repository.get_by_id(created.id)

        assert manager is not None
        assert manager.is_active is False
        assert manager.name == "Inactive"


# =============================================================================
# GET BY TELEGRAM ID
# =============================================================================


class TestGetByTelegramId:
    async def test_finds_by_telegram_id(
        self, supabase: AsyncClient, manager_repository: ManagerRepository,
    ):
        created = await create_test_manager(supabase, telegram_id=333, name="Bob")

        manager = await manager_repository.get_by_telegram_id(333)

        assert manager is not None
        assert manager.id == created.id
        assert manager.telegram_id == 333
        assert manager.name == "Bob"

    async def test_nonexistent_returns_none(
        self, manager_repository: ManagerRepository,
    ):
        result = await manager_repository.get_by_telegram_id(999999)
        assert result is None

    async def test_inactive_manager_still_found(
        self, supabase: AsyncClient, manager_repository: ManagerRepository,
    ):
        """Деактивированный менеджер находится по telegram_id.
        Критично: бот должен видеть менеджера для отображения имени.
        """
        await create_test_manager(
            supabase, telegram_id=444, name="Deactivated", is_active=False,
        )

        manager = await manager_repository.get_by_telegram_id(444)

        assert manager is not None
        assert manager.is_active is False
        assert manager.name == "Deactivated"


# =============================================================================
# GET ACTIVE BY ROLE
# =============================================================================


class TestGetActiveByRole:
    async def test_returns_active_accountants(
        self, supabase: AsyncClient, manager_repository: ManagerRepository,
    ):
        await create_test_manager(
            supabase, telegram_id=501, name="Accountant 1", role="accountant",
        )
        await create_test_manager(
            supabase, telegram_id=502, name="Accountant 2", role="accountant",
        )

        result = await manager_repository.get_active_by_role("accountant")

        assert len(result) == 2
        names = {m.name for m in result}
        assert names == {"Accountant 1", "Accountant 2"}
        assert all(m.role == "accountant" for m in result)

    async def test_excludes_inactive(
        self, supabase: AsyncClient, manager_repository: ManagerRepository,
    ):
        await create_test_manager(
            supabase, telegram_id=601, name="Active", role="accountant",
        )
        await create_test_manager(
            supabase, telegram_id=602, name="Inactive",
            role="accountant", is_active=False,
        )

        result = await manager_repository.get_active_by_role("accountant")

        assert len(result) == 1
        assert result[0].name == "Active"

    async def test_excludes_other_roles(
        self, supabase: AsyncClient, manager_repository: ManagerRepository,
    ):
        await create_test_manager(
            supabase, telegram_id=701, name="Manager", role="manager",
        )
        await create_test_manager(
            supabase, telegram_id=702, name="Accountant", role="accountant",
        )

        result = await manager_repository.get_active_by_role("accountant")

        assert len(result) == 1
        assert result[0].name == "Accountant"

    async def test_returns_empty_when_none_found(
        self, manager_repository: ManagerRepository,
    ):
        result = await manager_repository.get_active_by_role("accountant")
        assert result == []