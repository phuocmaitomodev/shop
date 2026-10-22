import asyncio
import base64
import hashlib
import hmac
import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-only-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://shop:shop@localhost:5432/shop_test"
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.session import get_db_session
from app.core.security import hash_password
from app.main import create_app
from app.models.auth import PasswordResetToken, User


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def auth_session_factory(tmp_path):
    database_path = tmp_path / "auth-test.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}", poolclass=NullPool
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare_database())
    try:
        yield session_factory
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def auth_client(auth_session_factory) -> TestClient:
    async def override_session():
        async with auth_session_factory() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_db_session] = override_session
    try:
        with TestClient(application) as test_client:
            yield test_client
    finally:
        application.dependency_overrides.clear()


@pytest.fixture
def create_auth_user(auth_session_factory):
    def create_user(
        email: str,
        password: str = "MatKhau-AnToan-123",
        role: str = "customer",
    ) -> None:
        async def persist_user() -> None:
            async with auth_session_factory() as session:
                session.add(
                    User(
                        email=email.lower(),
                        password_hash=hash_password(password),
                        full_name="Người Dùng Kiểm Thử",
                        role=role,
                    )
                )
                await session.commit()

        asyncio.run(persist_user())

    return create_user


@pytest.fixture
def get_demo_reset_token(auth_session_factory):
    def get_token(email: str) -> str:
        async def load_token_id():
            async with auth_session_factory() as session:
                return await session.scalar(
                    select(PasswordResetToken.id)
                    .join(User, User.id == PasswordResetToken.user_id)
                    .where(User.email == email.lower())
                    .order_by(PasswordResetToken.created_at.desc())
                    .limit(1)
                )

        token_id = asyncio.run(load_token_id())
        assert token_id is not None
        digest = hmac.new(
            b"test-only-secret", str(token_id).encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    return get_token
