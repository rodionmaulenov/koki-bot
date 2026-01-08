"""Тесты для UserService."""
import pytest


class TestUserServiceCreate:
    """Тесты для create()."""

    @pytest.mark.asyncio
    async def test_creates_user(self, user_service, test_manager):
        """Создаёт пользователя."""
        user = await user_service.create(
            name="Тест Девушка",
            manager_id=test_manager["id"],
        )

        assert user is not None
        assert user["name"] == "Тест Девушка"
        assert user["manager_id"] == test_manager["id"]
        assert user["telegram_id"] is None

    @pytest.mark.asyncio
    async def test_creates_user_with_id(self, user_service, test_manager):
        """Создаёт пользователя с id."""
        user = await user_service.create(
            name="Тест",
            manager_id=test_manager["id"],
        )

        assert "id" in user
        assert isinstance(user["id"], int)


class TestUserServiceGetById:
    """Тесты для get_by_id()."""

    @pytest.mark.asyncio
    async def test_finds_existing_user(self, user_service, test_user):
        """Находит существующего пользователя."""
        user = await user_service.get_by_id(test_user["id"])

        assert user is not None
        assert user["id"] == test_user["id"]
        assert user["name"] == test_user["name"]

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, user_service):
        """Возвращает None для несуществующего."""
        user = await user_service.get_by_id(999999999)

        assert user is None


class TestUserServiceGetByTelegramId:
    """Тесты для get_by_telegram_id()."""

    @pytest.mark.asyncio
    async def test_finds_user_with_telegram_id(self, user_service, test_user_with_telegram):
        """Находит пользователя по telegram_id."""
        user = await user_service.get_by_telegram_id(test_user_with_telegram["telegram_id"])

        assert user is not None
        assert user["id"] == test_user_with_telegram["id"]

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent(self, user_service):
        """Возвращает None для несуществующего telegram_id."""
        user = await user_service.get_by_telegram_id(999999999)

        assert user is None


class TestUserServiceSetTelegramId:
    """Тесты для set_telegram_id()."""

    @pytest.mark.asyncio
    async def test_sets_telegram_id(self, user_service, test_user):
        """Устанавливает telegram_id."""
        new_telegram_id = 123456789

        await user_service.set_telegram_id(test_user["id"], new_telegram_id)

        # Проверяем что обновилось
        user = await user_service.get_by_id(test_user["id"])
        assert user["telegram_id"] == new_telegram_id


class TestUserServiceSetTopicId:
    """Тесты для set_topic_id()."""

    @pytest.mark.asyncio
    async def test_sets_topic_id(self, user_service, test_user):
        """Устанавливает topic_id."""
        topic_id = 777

        await user_service.set_topic_id(test_user["id"], topic_id)

        # Проверяем что обновилось
        user = await user_service.get_by_id(test_user["id"])
        assert user["topic_id"] == topic_id


class TestGetByNameAndManager:
    """Тесты для get_by_name_and_manager."""

    @pytest.mark.asyncio
    async def test_finds_user(
        self,
        user_service,
        test_manager,
        supabase,
    ):
        """Находит user по имени и менеджеру."""
        # Создаём user
        result = await supabase.table("users").insert({
            "name": "Иванова Мария Петровна",
            "manager_id": test_manager["id"],
        }).execute()
        user_id = result.data[0]["id"]

        # Ищем
        found = await user_service.get_by_name_and_manager(
            name="Иванова Мария Петровна",
            manager_id=test_manager["id"],
        )

        assert found is not None
        assert found["id"] == user_id
        assert found["name"] == "Иванова Мария Петровна"

        # Cleanup
        await supabase.table("users").delete().eq("id", user_id).execute()

    @pytest.mark.asyncio
    async def test_returns_none_if_not_found(
        self,
        user_service,
        test_manager,
    ):
        """Возвращает None если user не найден."""
        found = await user_service.get_by_name_and_manager(
            name="Несуществующая Девушка",
            manager_id=test_manager["id"],
        )

        assert found is None

    @pytest.mark.asyncio
    async def test_not_finds_other_manager_user(
        self,
        user_service,
        test_manager,
        supabase,
    ):
        """НЕ находит user другого менеджера."""
        # Создаём другого менеджера
        other_manager = await supabase.table("managers").insert({
            "telegram_id": 999888777,
            "name": "Другой Менеджер",
            "is_active": True,
        }).execute()
        other_manager_id = other_manager.data[0]["id"]

        # Создаём user у другого менеджера
        user_result = await supabase.table("users").insert({
            "name": "Петрова Анна",
            "manager_id": other_manager_id,
        }).execute()
        user_id = user_result.data[0]["id"]

        # Ищем у test_manager — не должны найти
        found = await user_service.get_by_name_and_manager(
            name="Петрова Анна",
            manager_id=test_manager["id"],
        )

        assert found is None

        # Cleanup
        await supabase.table("users").delete().eq("id", user_id).execute()
        await supabase.table("managers").delete().eq("id", other_manager_id).execute()

    @pytest.mark.asyncio
    async def test_returns_latest_if_duplicates(
        self,
        user_service,
        test_manager,
        supabase,
    ):
        """Возвращает последнего созданного если несколько с одинаковым именем."""
        # Создаём первого user
        first = await supabase.table("users").insert({
            "name": "Дубликат Имя",
            "manager_id": test_manager["id"],
        }).execute()
        first_id = first.data[0]["id"]

        # Создаём второго user с тем же именем
        second = await supabase.table("users").insert({
            "name": "Дубликат Имя",
            "manager_id": test_manager["id"],
        }).execute()
        second_id = second.data[0]["id"]

        # Должен вернуть последнего (second)
        found = await user_service.get_by_name_and_manager(
            name="Дубликат Имя",
            manager_id=test_manager["id"],
        )

        assert found is not None
        assert found["id"] == second_id

        # Cleanup
        await supabase.table("users").delete().eq("id", first_id).execute()
        await supabase.table("users").delete().eq("id", second_id).execute()


class TestGetActiveByManager:
    """Тесты для get_active_by_manager."""

    @pytest.mark.asyncio
    async def test_returns_active_users(
        self,
        user_service,
        test_user_with_telegram,
        test_active_course,
        test_manager,
    ):
        """Возвращает девушек с активными курсами."""
        result = await user_service.get_active_by_manager(test_manager["id"])

        assert len(result) == 1
        assert result[0]["name"] == test_user_with_telegram["name"]

    @pytest.mark.asyncio
    async def test_returns_empty_if_no_active(
        self,
        user_service,
        test_manager,
    ):
        """Возвращает пустой список если нет активных."""
        result = await user_service.get_active_by_manager(test_manager["id"])

        assert result == []