"""Tests for ManagerRepository — real database, all 2 methods.

Key edge case: NO is_active filter — inactive managers are still returned.
This is intentional: deactivated managers must be findable for display on existing records.
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