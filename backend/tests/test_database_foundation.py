from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.base import metadata


EXPECTED_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def test_metadata_uses_stable_constraint_naming_convention() -> None:
    assert metadata.naming_convention == EXPECTED_NAMING_CONVENTION


def test_identity_metadata_defines_auth_tables() -> None:
    assert {"users", "auth_sessions", "password_reset_tokens"} <= set(metadata.tables)


def test_alembic_has_single_loadable_identity_head_that_enables_pgvector(
    monkeypatch,
) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(backend_dir / "alembic.ini")
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    scripts = ScriptDirectory.from_config(config)

    heads = scripts.get_heads()
    assert heads == ["0002_identity_auth"]

    identity_revision = scripts.get_revision(heads[0])
    assert identity_revision.down_revision == "0001_enable_pgvector"

    revision = scripts.get_revision("0001_enable_pgvector")
    executed_sql = []
    monkeypatch.setattr(revision.module.op, "execute", executed_sql.append)

    revision.module.upgrade()

    assert executed_sql == ["CREATE EXTENSION IF NOT EXISTS vector"]
