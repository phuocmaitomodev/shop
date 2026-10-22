from app.core.config import Settings


def test_settings_are_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-only-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://shop:shop@db:5432/shop")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:5173"]')

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.app_secret_key.get_secret_value() == "test-only-secret"
    assert str(settings.database_url) == "postgresql+asyncpg://shop:shop@db:5432/shop"
    assert settings.cors_allowed_origins == ["http://localhost:5173"]
