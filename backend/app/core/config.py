from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Shop API"
    app_env: Literal["development", "test", "production"] = "development"
    app_secret_key: SecretStr
    database_url: PostgresDsn
    log_level: str = "INFO"
    cors_allowed_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
