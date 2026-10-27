from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Shop API"
    app_env: Literal["development", "test", "production"] = "development"
    app_secret_key: SecretStr
    database_url: PostgresDsn
    log_level: str = "INFO"
    cors_allowed_origins: list[str] = ["http://localhost:5176"]
    auth_session_ttl_days: int = Field(default=7, gt=0)
    auth_cookie_name: str = "shop_session"
    auth_cookie_secure: bool = False
    password_reset_ttl_minutes: int = Field(default=30, gt=0)
    auth_rate_limit_attempts: int = Field(default=20, gt=0)
    auth_rate_limit_window_seconds: int = Field(default=60, gt=0)
    auth_rate_limit_max_keys: int = Field(default=10_000, gt=0)
    forgot_response_floor_ms: int = Field(default=250, ge=0)
    chat_rate_limit_requests: int = Field(default=30, gt=0)
    chat_rate_limit_window_seconds: int = Field(default=60, gt=0)
    rag_embedding_provider: Literal["stub", "gemini"] = "stub"
    rag_chat_provider: Literal["stub", "gemini"] = "stub"
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    gemini_embedding_model: str | None = None
    embedding_dimension: int = Field(default=768, gt=0)
    rag_worker_lock_timeout_seconds: int = Field(default=300, gt=0)
    rag_worker_provider_timeout_seconds: float = Field(default=120.0, gt=0)
    rag_worker_max_attempts: int = Field(default=5, gt=0)
    rag_worker_retry_base_seconds: int = Field(default=5, gt=0)
    rag_worker_retry_max_seconds: int = Field(default=300, gt=0)
    rag_worker_poll_seconds: float = Field(default=2.0, gt=0)
    rag_worker_health_max_age_seconds: float = Field(default=150.0, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def require_secure_production_cookie(self) -> "Settings":
        if self.app_env == "production" and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        if self.embedding_dimension != 768:
            raise ValueError("EMBEDDING_DIMENSION must be 768 for the current migration")
        if self.rag_embedding_provider == "gemini" and (
            self.gemini_api_key is None
            or not self.gemini_api_key.get_secret_value()
            or not self.gemini_embedding_model
            or not self.gemini_embedding_model.strip()
        ):
            raise ValueError(
                "GEMINI_API_KEY and GEMINI_EMBEDDING_MODEL are required "
                "when RAG_EMBEDDING_PROVIDER=gemini"
            )
        if self.rag_chat_provider == "gemini" and (
            self.gemini_api_key is None
            or not self.gemini_api_key.get_secret_value()
            or not self.gemini_model
            or not self.gemini_model.strip()
        ):
            raise ValueError(
                "GEMINI_API_KEY and GEMINI_MODEL are required "
                "when RAG_CHAT_PROVIDER=gemini"
            )
        if self.rag_worker_retry_max_seconds < self.rag_worker_retry_base_seconds:
            raise ValueError(
                "RAG_WORKER_RETRY_MAX_SECONDS must be greater than or equal to "
                "RAG_WORKER_RETRY_BASE_SECONDS"
            )
        if not (
            self.rag_worker_poll_seconds
            < self.rag_worker_health_max_age_seconds
            < self.rag_worker_lock_timeout_seconds
        ):
            raise ValueError(
                "RAG_WORKER_HEALTH_MAX_AGE_SECONDS must be greater than "
                "RAG_WORKER_POLL_SECONDS and less than "
                "RAG_WORKER_LOCK_TIMEOUT_SECONDS"
            )
        if (
            self.rag_worker_provider_timeout_seconds
            >= self.rag_worker_lock_timeout_seconds
        ):
            raise ValueError(
                "RAG_WORKER_PROVIDER_TIMEOUT_SECONDS must be less than "
                "RAG_WORKER_LOCK_TIMEOUT_SECONDS"
            )
        if (
            self.rag_worker_health_max_age_seconds
            <= self.rag_worker_provider_timeout_seconds
        ):
            raise ValueError(
                "RAG_WORKER_HEALTH_MAX_AGE_SECONDS must be greater than "
                "RAG_WORKER_PROVIDER_TIMEOUT_SECONDS"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
