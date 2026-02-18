"""Tests for OwnerRepository — real database, 1 method.

Key edge case: NO is_active filter — inactive owners are still returned.
"""
from supabase import AsyncClient

from repositories.owner_repository import OwnerRepository
from tests.conftest import create_test_owner


# =============================================================================
# GET BY TELEGRAM ID
# =============================================================================


class TestGetByTelegramId:
    async def test_returns_owner_with_all_fields(
        self, supabase: AsyncClient, owner_repository: OwnerRepository,
    ):
        created = await create_test_owner(supabase, telegram_id=111, name="Owner One")

        owner = await owner_repository.get_by_telegram_id(111)

        assert owner is not None
        assert owner.id == created.id
        assert owner.telegram_id == 111
        assert owner.name == "Owner One"
        assert owner.is_active is True
        assert owner.created_at is not None

    async def test_nonexistent_returns_none(
        self, owner_repository: OwnerRepository,
    ):
        result = await owner_repository.get_by_telegram_id(999999)
        assert result is None

    async def test_inactive_owner_still_found(
        self, supabase: AsyncClient, owner_repository: OwnerRepository,
    ):
        """is_active=False — владелец всё равно возвращается.
        Если кто-то добавит .eq("is_active", True) — тест упадёт.
        """
        await create_test_owner(
            supabase, telegram_id=222, name="Inactive Owner", is_active=False,
        )

        owner = await owner_repository.get_by_telegram_id(222)

        assert owner is not None
        assert owner.is_active is False
        assert owner.name == "Inactive Owner"