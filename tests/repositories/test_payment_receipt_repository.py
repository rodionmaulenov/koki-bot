"""Tests for PaymentReceiptRepository — create, get_by_course_id."""

import pytest
from supabase import AsyncClient

from repositories.payment_receipt_repository import PaymentReceiptRepository
from tests.conftest import (
    create_test_course,
    create_test_manager,
    create_test_payment_receipt,
    create_test_user,
)


class TestCreate:
    async def test_creates_receipt(
        self, supabase: AsyncClient,
        payment_receipt_repository: PaymentReceiptRepository,
    ) -> None:
        manager = await create_test_manager(supabase)
        user = await create_test_user(supabase, manager_id=manager.id)
        course = await create_test_course(supabase, user_id=user.id)

        receipt = await payment_receipt_repository.create(
            course_id=course.id,
            accountant_id=manager.id,
            receipt_file_id="file_abc",
            amount=150000,
        )

        assert receipt.course_id == course.id
        assert receipt.accountant_id == manager.id
        assert receipt.receipt_file_id == "file_abc"
        assert receipt.amount == 150000
        assert receipt.id > 0

    async def test_creates_receipt_without_amount(
        self, supabase: AsyncClient,
        payment_receipt_repository: PaymentReceiptRepository,
    ) -> None:
        manager = await create_test_manager(supabase)
        user = await create_test_user(supabase, manager_id=manager.id)
        course = await create_test_course(supabase, user_id=user.id)

        receipt = await payment_receipt_repository.create(
            course_id=course.id,
            accountant_id=manager.id,
            receipt_file_id="file_abc",
        )

        assert receipt.amount is None

    async def test_unique_constraint_on_course_id(
        self, supabase: AsyncClient,
        payment_receipt_repository: PaymentReceiptRepository,
    ) -> None:
        manager = await create_test_manager(supabase)
        user = await create_test_user(supabase, manager_id=manager.id)
        course = await create_test_course(supabase, user_id=user.id)

        await payment_receipt_repository.create(
            course_id=course.id,
            accountant_id=manager.id,
            receipt_file_id="file_first",
        )

        with pytest.raises(Exception):
            await payment_receipt_repository.create(
                course_id=course.id,
                accountant_id=manager.id,
                receipt_file_id="file_second",
            )


class TestGetByCourseId:
    async def test_returns_receipt(
        self, supabase: AsyncClient,
        payment_receipt_repository: PaymentReceiptRepository,
    ) -> None:
        manager = await create_test_manager(supabase)
        user = await create_test_user(supabase, manager_id=manager.id)
        course = await create_test_course(supabase, user_id=user.id)
        created = await create_test_payment_receipt(
            supabase, course_id=course.id, accountant_id=manager.id,
        )

        result = await payment_receipt_repository.get_by_course_id(course.id)

        assert result is not None
        assert result.id == created.id
        assert result.course_id == course.id
        assert result.receipt_file_id == "test_payment_receipt_file_id"
        assert result.amount == 150000

    async def test_returns_none_when_not_found(
        self, payment_receipt_repository: PaymentReceiptRepository,
    ) -> None:
        result = await payment_receipt_repository.get_by_course_id(999999)
        assert result is None
