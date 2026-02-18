"""Tests for DocumentRepository — get_by_user_id."""

import pytest
from supabase import AsyncClient

from repositories.document_repository import DocumentRepository
from tests.conftest import create_test_document, create_test_manager, create_test_user


class TestGetByUserId:
    async def test_returns_document(
        self, supabase: AsyncClient, document_repository: DocumentRepository,
    ) -> None:
        manager = await create_test_manager(supabase)
        user = await create_test_user(supabase, manager_id=manager.id)
        doc = await create_test_document(supabase, user_id=user.id, manager_id=manager.id)

        result = await document_repository.get_by_user_id(user.id)

        assert result is not None
        assert result.id == doc.id
        assert result.user_id == user.id
        assert result.manager_id == manager.id
        assert result.passport_file_id == "test_passport_file_id"
        assert result.receipt_file_id == "test_receipt_file_id"
        assert result.receipt_price == 150000
        assert result.card_file_id == "test_card_file_id"
        assert result.card_number == "8600123456789012"
        assert result.card_holder_name == "IVANOVA MARINA"

    async def test_returns_none_when_not_found(
        self, document_repository: DocumentRepository,
    ) -> None:
        result = await document_repository.get_by_user_id(999999)
        assert result is None

    async def test_returns_document_with_null_fields(
        self, supabase: AsyncClient, document_repository: DocumentRepository,
    ) -> None:
        manager = await create_test_manager(supabase)
        user = await create_test_user(supabase, manager_id=manager.id)
        await create_test_document(
            supabase, user_id=user.id, manager_id=manager.id,
            passport_file_id=None, receipt_price=None, card_number=None,
            card_holder_name=None, card_file_id=None, receipt_file_id=None,
        )

        result = await document_repository.get_by_user_id(user.id)

        assert result is not None
        assert result.passport_file_id is None
        assert result.receipt_price is None
        assert result.card_number is None
        assert result.card_holder_name is None
