import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


MIGRATION_DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not MIGRATION_DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for PostgreSQL migration tests",
)


async def _database_state(database_url: str) -> tuple[set[str], set[str], set[str]]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            tables = set(
                await connection.scalars(
                    text(
                        "SELECT tablename FROM pg_catalog.pg_tables "
                        "WHERE schemaname = 'public'"
                    )
                )
            )
            extensions = set(
                await connection.scalars(text("SELECT extname FROM pg_extension"))
            )
            revisions = set()
            if "alembic_version" in tables:
                revisions = set(
                    await connection.scalars(text("SELECT version_num FROM alembic_version"))
                )
            return tables, extensions, revisions
    finally:
        await engine.dispose()


def test_upgrade_head_on_fresh_postgresql_with_pgvector() -> None:
    assert MIGRATION_DATABASE_URL is not None
    assert MIGRATION_DATABASE_URL.startswith("postgresql+asyncpg://")

    backend_dir = Path(__file__).resolve().parents[2]
    alembic_config = Config(backend_dir / "alembic.ini")
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    expected_head = ScriptDirectory.from_config(alembic_config).get_current_head()
    expected_tables = {
        "alembic_version",
        "auth_sessions",
        "categories",
        "colors",
        "labels",
        "password_reset_tokens",
        "product_images",
        "product_labels",
        "product_variants",
        "products",
        "knowledge_documents",
        "rag_chunks",
        "rag_documents",
        "rag_index_jobs",
        "sizes",
        "users",
    }

    tables_before, extensions_before, revisions_before = asyncio.run(
        _database_state(MIGRATION_DATABASE_URL)
    )
    assert tables_before == set(), "migration database must start without public tables"
    assert "vector" not in extensions_before
    assert revisions_before == set()

    environment = os.environ.copy()
    environment["DATABASE_URL"] = MIGRATION_DATABASE_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=backend_dir,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    tables_after, extensions_after, revisions_after = asyncio.run(
        _database_state(MIGRATION_DATABASE_URL)
    )
    assert expected_tables <= tables_after
    assert "vector" in extensions_after
    assert revisions_after == {expected_head}
