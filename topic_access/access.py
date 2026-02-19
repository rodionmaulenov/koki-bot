from repositories.manager_repository import ManagerRepository


async def has_access(
    telegram_id: int,
    manager_repository: ManagerRepository,
) -> bool:
    manager = await manager_repository.get_by_telegram_id(telegram_id)
    return manager is not None
