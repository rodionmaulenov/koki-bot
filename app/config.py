from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    bot_token: str
    supabase_url: str
    supabase_key: str
    gemini_api_key: str
    redis_url: str = "redis://localhost:6379/0"

    # Группа команд (общая для всех проектов)
    commands_group_id: int
    general_thread_id: int = 0  # 0 = General топик (без message_thread_id)
    commands_thread_id: int
    rules_message_id: int | None = None

    # Группа КОК (топики девушек)
    kok_group_id: int

    # Дашборд
    dashboard_type: str = "kok_dashboard"

    class Config:
        env_file = BASE_DIR / ".env"
        case_sensitive = False
        extra = "ignore"

@lru_cache
def get_settings() -> Settings:
    return Settings()