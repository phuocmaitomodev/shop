import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://shop:shop@localhost:5432/shop_test"
)

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client
