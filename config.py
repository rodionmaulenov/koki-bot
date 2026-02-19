import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent

IS_TEST_MODE = os.getenv("ENV") == "test"


class Settings(BaseSettings):
    bot_token: str
    supabase_url: str
    supabase_key: str
    redis_url: str = "redis://localhost:6379/0"

    commands_group_id: int
    commands_thread_id: int
    kok_group_id: int
    kok_general_topic_id: int = 0  # 0 = General топик (без message_thread_id)

    bot_type: str = "kok"

    gemini_api_key: str = ""

    # Sentry error tracking
    sentry_dsn: str | None = None

    # Telegram error notifications (errors sent to topic)
    error_topic_chat_id: int | None = None
    error_topic_id: int | None = None

    # Seed data for development mode (optional)
    seed_manager_id: int | None = None
    seed_manager_name: str | None = None

    class Config:
        env_file = BASE_DIR / (".env.test" if IS_TEST_MODE else ".env")
        case_sensitive = False
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
