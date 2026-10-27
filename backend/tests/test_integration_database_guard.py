import pytest

from tests.integration.database_guard import (
    mark_fresh_migrated_database,
    require_fresh_migrated_database,
)


def test_database_guard_rejects_unverified_database_before_destructive_setup() -> None:
    with pytest.raises(RuntimeError, match="refusing destructive"):
        require_fresh_migrated_database("postgresql+asyncpg://example/reused")


def test_database_guard_accepts_database_verified_in_this_pytest_run() -> None:
    database_url = "postgresql+asyncpg://example/fresh"

    mark_fresh_migrated_database(database_url)

    require_fresh_migrated_database(database_url)
