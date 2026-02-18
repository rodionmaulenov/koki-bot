"""Tests for UserRepository — real database, all 6 methods."""
from supabase import AsyncClient

from repositories.user_repository import UserRepository
from tests.conftest import create_test_manager, create_test_user


# =============================================================================
# GET BY ID
# =============================================================================


class TestGetById:
    async def test_returns_user_with_all_fields(
        self, supabase: AsyncClient, make_user, user_repository: UserRepository,
    ):
        _, user_id = make_user

        user = await user_repository.get_by_id(user_id)

        assert user is not None
        assert user.id == user_id
        assert user.name == "Ivanova Marina Alexandrovna"
        assert user.telegram_id is None
        assert user.topic_id is None
        assert user.created_at is not None

    async def test_nonexistent_returns_none(
        self, user_repository: UserRepository,
    ):
        result = await user_repository.get_by_id(999999)
        assert result is None


# =============================================================================
# GET BY TELEGRAM ID
# =============================================================================


class TestGetByTelegramId:
    async def test_finds_by_telegram_id(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        manager = await create_test_manager(supabase)
        user = await create_test_user(
            supabase, manager_id=manager.id, telegram_id=12345,
        )

        found = await user_repository.get_by_telegram_id(12345)

        assert found is not None
        assert found.id == user.id
        assert found.telegram_id == 12345

    async def test_nonexistent_returns_none(
        self, user_repository: UserRepository,
    ):
        result = await user_repository.get_by_telegram_id(999999)
        assert result is None

    async def test_null_telegram_id_not_matched(
        self, make_user, user_repository: UserRepository,
    ):
        """User exists with telegram_id=None — search by any ID won't find it."""
        # make_user creates user without telegram_id (default=None)
        result = await user_repository.get_by_telegram_id(12345)
        assert result is None


# =============================================================================
# GET BY MANAGER ID
# =============================================================================


class TestGetByManagerId:
    async def test_returns_all_users_for_manager(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        manager = await create_test_manager(supabase)
        u1 = await create_test_user(
            supabase, manager_id=manager.id, name="User One",
        )
        u2 = await create_test_user(
            supabase, manager_id=manager.id, name="User Two",
        )

        users = await user_repository.get_by_manager_id(manager.id)

        assert len(users) == 2
        user_ids = {u.id for u in users}
        assert u1.id in user_ids
        assert u2.id in user_ids

    async def test_empty_for_nonexistent_manager(
        self, user_repository: UserRepository,
    ):
        result = await user_repository.get_by_manager_id(999999)
        assert result == []

    async def test_does_not_return_other_managers_users(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        m1 = await create_test_manager(supabase, telegram_id=111, name="Manager 1")
        m2 = await create_test_manager(supabase, telegram_id=222, name="Manager 2")
        await create_test_user(supabase, manager_id=m1.id, name="User of M1")
        await create_test_user(supabase, manager_id=m2.id, name="User of M2")

        users_m1 = await user_repository.get_by_manager_id(m1.id)

        assert len(users_m1) == 1
        assert users_m1[0].name == "User of M1"


# =============================================================================
# GET BY NAME PREFIX AND BIRTH DATE (deduplication via OCR)
# =============================================================================


class TestGetByNamePrefixAndBirthDate:
    """Dedup: OCR распознал ФИО + дату рождения → ищем существующего пользователя.
    Паттерн ilike: "{last_name} {first_name}%" — фамилия + имя, отчество может отличаться.
    """

    async def test_finds_exact_match(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        manager = await create_test_manager(supabase)
        user = await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Marina Alexandrovna", birth_date="01.01.2000",
        )

        found = await user_repository.get_by_name_prefix_and_birth_date(
            "Ivanova", "Marina", "01.01.2000",
        )

        assert found is not None
        assert found.id == user.id

    async def test_prefix_matches_with_patronymic(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        """Pattern "{last} {first}%" matches name with any patronymic."""
        manager = await create_test_manager(supabase)
        await create_test_user(
            supabase, manager_id=manager.id,
            name="Sidorova Anna Petrovna", birth_date="15.06.1995",
        )

        found = await user_repository.get_by_name_prefix_and_birth_date(
            "Sidorova", "Anna", "15.06.1995",
        )

        assert found is not None
        assert found.name == "Sidorova Anna Petrovna"

    async def test_case_insensitive(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        """ilike — регистронезависимый. OCR может вернуть разный регистр."""
        manager = await create_test_manager(supabase)
        await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Marina Alexandrovna", birth_date="01.01.2000",
        )

        found = await user_repository.get_by_name_prefix_and_birth_date(
            "ivanova", "marina", "01.01.2000",
        )

        assert found is not None

    async def test_wrong_birth_date_returns_none(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        """Имя совпадает, дата рождения нет — защита от однофамильцев."""
        manager = await create_test_manager(supabase)
        await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Marina Alexandrovna", birth_date="01.01.2000",
        )

        result = await user_repository.get_by_name_prefix_and_birth_date(
            "Ivanova", "Marina", "02.02.1999",
        )

        assert result is None

    async def test_wrong_name_returns_none(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        """Дата совпадает, имя нет."""
        manager = await create_test_manager(supabase)
        await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Marina Alexandrovna", birth_date="01.01.2000",
        )

        result = await user_repository.get_by_name_prefix_and_birth_date(
            "Petrova", "Anna", "01.01.2000",
        )

        assert result is None

    async def test_partial_last_name_does_not_match(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        """'Ivan' НЕ совпадает с 'Ivanova' — паттерн 'Ivan Marina%' ≠ 'Ivanova Marina...'"""
        manager = await create_test_manager(supabase)
        await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Marina Alexandrovna", birth_date="01.01.2000",
        )

        result = await user_repository.get_by_name_prefix_and_birth_date(
            "Ivan", "Marina", "01.01.2000",
        )

        assert result is None

    async def test_returns_one_when_multiple_match(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        """Две тёзки с одной датой рождения → limit(1) возвращает одну, не падает."""
        manager = await create_test_manager(supabase)
        await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Marina Alexandrovna", birth_date="01.01.2000",
        )
        await create_test_user(
            supabase, manager_id=manager.id,
            name="Ivanova Marina Petrovna", birth_date="01.01.2000",
        )

        found = await user_repository.get_by_name_prefix_and_birth_date(
            "Ivanova", "Marina", "01.01.2000",
        )

        assert found is not None


# =============================================================================
# SET TELEGRAM ID
# =============================================================================


class TestSetTelegramId:
    async def test_sets_telegram_id(
        self, supabase: AsyncClient, make_user, user_repository: UserRepository,
    ):
        _, user_id = make_user

        await user_repository.set_telegram_id(user_id, 12345)

        updated = await user_repository.get_by_id(user_id)
        assert updated.telegram_id == 12345

    async def test_overwrites_existing(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        manager = await create_test_manager(supabase)
        user = await create_test_user(
            supabase, manager_id=manager.id, telegram_id=111,
        )

        await user_repository.set_telegram_id(user.id, 222)

        updated = await user_repository.get_by_id(user.id)
        assert updated.telegram_id == 222


# =============================================================================
# SET TOPIC ID
# =============================================================================


class TestSetTopicId:
    async def test_sets_topic_id(
        self, supabase: AsyncClient, make_user, user_repository: UserRepository,
    ):
        _, user_id = make_user

        await user_repository.set_topic_id(user_id, 9999)

        updated = await user_repository.get_by_id(user_id)
        assert updated.topic_id == 9999

    async def test_overwrites_existing(
        self, supabase: AsyncClient, user_repository: UserRepository,
    ):
        manager = await create_test_manager(supabase)
        user = await create_test_user(
            supabase, manager_id=manager.id, topic_id=100,
        )

        await user_repository.set_topic_id(user.id, 200)

        updated = await user_repository.get_by_id(user.id)
        assert updated.topic_id == 200
