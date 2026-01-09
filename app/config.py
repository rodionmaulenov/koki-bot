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
    manager_group_id: int
    commands_thread_id: int
    general_thread_id: int
    rules_message_id: int | None = None

    class Config:
        env_file = BASE_DIR / ".env"
        case_sensitive = False
        extra = "ignore"

@lru_cache
def get_settings() -> Settings:
    return Settings()


