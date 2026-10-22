import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_are_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:5173"]')
    monkeypatch.setenv("AUTH_SESSION_TTL_DAYS", "14")
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "20")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.app_secret_key.get_secret_value() == "test-only-secret"
    assert str(settings.database_url) == "postgresql+asyncpg://shop:shop@db:5432/shop"
    assert settings.cors_allowed_origins == ["http://localhost:5173"]
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
