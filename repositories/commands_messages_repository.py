from supabase import AsyncClient

from models.commands_message import CommandsMessage


class CommandsMessagesRepository:
    def __init__(self, supabase: AsyncClient, bot_type: str) -> None:
        self._supabase = supabase
        self._bot_type = bot_type

    async def add_message(self, message_id: int, is_menu: bool = False) -> None:
        await (
            self._supabase.schema("public")
            .table("commands_messages")
            .insert({
                "message_id": message_id,
                "bot_type": self._bot_type,
                "is_menu": is_menu,
            })
            .execute()
        )

    async def get_non_menu_messages(self) -> list[CommandsMessage]:
        response = await (
            self._supabase.schema("public")
            .table("commands_messages")
            .select("id, message_id, bot_type, is_menu, created_at")
            .eq("bot_type", self._bot_type)
            .eq("is_menu", False)
            .execute()
        )
        return [CommandsMessage(**row) for row in response.data]

    async def get_menu_message(self) -> CommandsMessage | None:
        response = await (
            self._supabase.schema("public")
            .table("commands_messages")
            .select("id, message_id, bot_type, is_menu, created_at")
            .eq("bot_type", self._bot_type)
            .eq("is_menu", True)
            .limit(1)
            .execute()
        )
        if response.data:
            return CommandsMessage(**response.data[0])
        return None

    async def delete_by_ids(self, ids: list[int]) -> None:
        if not ids:
            return
        await (
            self._supabase.schema("public")
            .table("commands_messages")
            .delete()
            .in_("id", ids)
            .execute()
        )

    async def delete_by_message_id(self, message_id: int) -> None:
        await (
            self._supabase.schema("public")
            .table("commands_messages")
            .delete()
            .eq("message_id", message_id)
            .eq("bot_type", self._bot_type)
            .execute()
        )

    async def delete_menu_message(self) -> None:
        await (
            self._supabase.schema("public")
            .table("commands_messages")
            .delete()
            .eq("bot_type", self._bot_type)
            .eq("is_menu", True)
            .execute()
        )
