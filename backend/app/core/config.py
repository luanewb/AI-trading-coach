from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(default="postgresql+psycopg://trading:trading@postgres:5432/tradingcoach")
    redis_url: str = Field(default="redis://redis:6379/0")
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    enable_ai: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    api_key: str = "change-me"
    ftmo_timezone: str = "Europe/Prague"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
