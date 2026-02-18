from repositories.manager_repository import ManagerRepository
from repositories.owner_repository import OwnerRepository


async def has_access(
    telegram_id: int,
    manager_repository: ManagerRepository,
    owner_repository: OwnerRepository,
) -> bool:
    manager = await manager_repository.get_by_telegram_id(telegram_id)
    if manager:
        return True
    owner = await owner_repository.get_by_telegram_id(telegram_id)
    return owner is not None
