_FRESH_MIGRATED_DATABASES: set[str] = set()


def mark_fresh_migrated_database(database_url: str) -> None:
    """Authorize destructive setup only after this pytest run migrated an empty DB."""
    _FRESH_MIGRATED_DATABASES.add(database_url)


def require_fresh_migrated_database(database_url: str) -> None:
    if database_url not in _FRESH_MIGRATED_DATABASES:
        raise RuntimeError(
            "refusing destructive integration-test setup: this pytest run did not "
            "verify and migrate an empty PostgreSQL database"
        )
