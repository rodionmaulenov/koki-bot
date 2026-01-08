"""Подключение к базе данных."""

from supabase._async.client import create_client as acreate_client

from app.config import get_settings

settings = get_settings()

_supabase = None


async def get_supabase():
    """Возвращает async клиент Supabase."""
    global _supabase
    if _supabase is None:
        _supabase = await acreate_client(
            settings.supabase_url,
            settings.supabase_key,
        )
    return _supabase