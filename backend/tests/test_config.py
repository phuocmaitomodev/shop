import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_are_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:5176"]')
    monkeypatch.setenv("AUTH_SESSION_TTL_DAYS", "14")
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "20")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.app_secret_key.get_secret_value() == "test-only-secret"
    assert str(settings.database_url) == "postgresql+asyncpg://shop:shop@db:5432/shop"
    assert settings.cors_allowed_origins == ["http://localhost:5176"]
    assert settings.auth_session_ttl_days == 14
    assert settings.password_reset_ttl_minutes == 20


def test_production_requires_secure_auth_cookie(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("APP_SECRET_KEY", "production-placeholder-for-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_auth_ttls_must_be_positive(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")
    monkeypatch.setenv("AUTH_SESSION_TTL_DAYS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rag_worker_settings_have_safe_defaults(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")
    monkeypatch.delenv("EMBEDDING_DIMENSION", raising=False)

    settings = Settings(_env_file=None)

    assert settings.rag_embedding_provider == "stub"
    assert settings.gemini_api_key is None
    assert settings.gemini_embedding_model is None
    assert settings.embedding_dimension == 768
    assert settings.rag_worker_lock_timeout_seconds == 300
    assert settings.rag_worker_provider_timeout_seconds == 120.0
    assert settings.rag_worker_max_attempts == 5
    assert settings.rag_worker_retry_base_seconds == 5
    assert settings.rag_worker_retry_max_seconds == 300
    assert settings.rag_worker_poll_seconds == 2.0
    assert settings.rag_worker_health_max_age_seconds == 150.0


def test_gemini_embedding_provider_requires_key_and_model(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_EMBEDDING_MODEL", raising=False)

    with pytest.raises(
        ValidationError, match="GEMINI_API_KEY and GEMINI_EMBEDDING_MODEL"
    ):
        Settings(_env_file=None)


def test_gemini_embedding_provider_loads_secret_and_model(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "configured-test-key")
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "configured-model")

    settings = Settings(_env_file=None)

    assert settings.rag_embedding_provider == "gemini"
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "configured-test-key"
    assert settings.gemini_embedding_model == "configured-model"


def test_embedding_dimension_must_match_migrated_vector_dimension(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1536")

    with pytest.raises(ValidationError, match="EMBEDDING_DIMENSION must be 768"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    (
        "poll_seconds",
        "health_max_age_seconds",
        "provider_timeout_seconds",
        "lock_timeout_seconds",
    ),
    [
        (10, 5, 120, 300),
        (2, 300, 120, 300),
        (2, 150, 300, 300),
        (2, 100, 120, 300),
    ],
)
def test_worker_health_window_must_be_between_poll_and_lease(
    monkeypatch,
    poll_seconds: int,
    health_max_age_seconds: int,
    provider_timeout_seconds: int,
    lock_timeout_seconds: int,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")
    monkeypatch.setenv("RAG_WORKER_POLL_SECONDS", str(poll_seconds))
    monkeypatch.setenv(
        "RAG_WORKER_HEALTH_MAX_AGE_SECONDS", str(health_max_age_seconds)
    )
    monkeypatch.setenv(
        "RAG_WORKER_PROVIDER_TIMEOUT_SECONDS", str(provider_timeout_seconds)
    )
    monkeypatch.setenv("RAG_WORKER_LOCK_TIMEOUT_SECONDS", str(lock_timeout_seconds))

    with pytest.raises(
        ValidationError,
        match="RAG_WORKER_(HEALTH_MAX_AGE|PROVIDER_TIMEOUT)_SECONDS",
    ):
        Settings(_env_file=None)
