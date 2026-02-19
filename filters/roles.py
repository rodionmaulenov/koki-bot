import logging

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message
from dishka import AsyncContainer

from models.enums import ManagerRole
from repositories.manager_repository import ManagerRepository

logger = logging.getLogger(__name__)


class RoleFilter(Filter):
    """Router-level filter that checks if the user has one of the allowed roles.

    Uses Dishka container to resolve ManagerRepository (Dishka only
    auto-injects into handlers, not filters).

    Returns {"manager": Manager} on success so handlers can use it as a kwarg.
    """

    def __init__(self, *allowed_roles: ManagerRole) -> None:
        self._allowed_roles = set(allowed_roles)

    async def __call__(
        self,
        event: Message | CallbackQuery,
        dishka_container: AsyncContainer,
    ) -> dict | bool:
        user = event.from_user
        if not user:
            return False

        manager_repository = await dishka_container.get(ManagerRepository)
        manager = await manager_repository.get_by_telegram_id(user.id)
        if manager is None or manager.role not in self._allowed_roles:
            return False

        return {"manager": manager}
