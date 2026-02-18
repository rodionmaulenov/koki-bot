import pytest
from supabase import AsyncClient

from tests.conftest import create_test_course, create_test_manager, create_test_user


@pytest.fixture(autouse=True)
async def auto_cleanup_db(cleanup_db):
    """Автоочистка БД до/после каждого теста в этой папке."""
    yield


@pytest.fixture
async def make_user(supabase: AsyncClient):
    """Создать manager + user, вернуть (manager_id, user_id)."""
    manager = await create_test_manager(supabase)
    user = await create_test_user(supabase, manager_id=manager.id)
    return manager.id, user.id


@pytest.fixture
async def make_course(supabase: AsyncClient, make_user):
    """Создать manager + user + active course, вернуть Course."""
    _, user_id = make_user
    return await create_test_course(supabase, user_id=user_id, status="active")