import logging
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest
from redis.asyncio import Redis
from supabase import AsyncClient

from config import IS_TEST_MODE, Settings

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)


class DevModeService:
    def __init__(
        self,
        supabase: AsyncClient,
        redis: Redis,
        settings: Settings,
        bot: "Bot | None" = None,
    ) -> None:
        self._supabase = supabase
        self._redis = redis
        self._settings = settings
        self._bot = bot

    async def startup(self) -> None:
        await self._cleanup_database()
        await self._cleanup_redis()
        await self._seed_database()

    async def shutdown(self) -> None:
        await self._delete_menu_from_telegram()
        await self._cleanup_database()
        await self._cleanup_redis()

    async def _cleanup_database(self) -> None:
        if not IS_TEST_MODE:
            return

        logger.info("Cleaning up database (dev mode)...")

        # Delete kok tables (order matters: FK dependencies)
        for table in ("intake_logs", "courses", "documents", "users"):
            await (
                self._supabase.schema("kok")
                .table(table)
                .delete()
                .neq("id", 0)
                .execute()
            )
        logger.debug("Deleted all kok data")

        # Delete seed users
        if self._settings.seed_manager_id:
            await (
                self._supabase.schema("public")
                .table("managers")
                .delete()
                .eq("telegram_id", self._settings.seed_manager_id)
                .execute()
            )

        # Delete commands_messages for this bot_type
        await (
            self._supabase.schema("public")
            .table("commands_messages")
            .delete()
            .eq("bot_type", self._settings.bot_type)
            .execute()
        )

        logger.info("Database cleanup complete")

    async def _cleanup_redis(self) -> None:
        if not IS_TEST_MODE:
            return

        logger.info("Cleaning up Redis (dev mode)...")

        fsm_keys = await self._redis.keys("fsm:*")
        if fsm_keys:
            await self._redis.delete(*fsm_keys)
            logger.debug("Deleted %d FSM keys", len(fsm_keys))

        logger.info("Redis cleanup complete")

    async def _seed_database(self) -> None:
        if not IS_TEST_MODE:
            return

        logger.info("Seeding database (dev mode)...")

        if self._settings.seed_manager_id and self._settings.seed_manager_name:
            await (
                self._supabase.schema("public")
                .table("managers")
                .insert({
                    "telegram_id": self._settings.seed_manager_id,
                    "name": self._settings.seed_manager_name,
                    "is_active": True,
                })
                .execute()
            )
            logger.info("Created manager: %s", self._settings.seed_manager_name)

        logger.info("Database seeding complete")

    async def _delete_menu_from_telegram(self) -> None:
        if not IS_TEST_MODE or not self._bot:
            return

        try:
            result = await (
                self._supabase.schema("public")
                .table("commands_messages")
                .select("message_id")
                .eq("bot_type", self._settings.bot_type)
                .eq("is_menu", True)
                .limit(1)
                .execute()
            )

            if result.data:
                row: dict = result.data[0]  # type: ignore[assignment]
                message_id = int(row["message_id"])
                try:
                    await self._bot.delete_message(
                        chat_id=self._settings.commands_group_id,
                        message_id=message_id,
                    )
                    logger.info("Deleted menu message %d from Telegram", message_id)
                except TelegramBadRequest as e:
                    logger.debug("Could not delete menu message: %s", e)
        except Exception as e:
            logger.debug("Error deleting menu from Telegram: %s", e)
