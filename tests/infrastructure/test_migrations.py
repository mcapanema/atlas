from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

import app.infrastructure.repositories  # noqa: F401  # registers ORM models on Base.metadata
from app.config import get_settings
from app.infrastructure.database.base import Base


def test_upgrade_head_matches_orm_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every migration on a fresh DB and diff the result against the models.

    `uv run alembic check` as a test — model/migration drift fails the suite
    instead of failing on deploy. Sync `def` on purpose: migrations/env.py
    calls asyncio.run(), which must not run inside an existing event loop.
    """
    db_path = tmp_path / "migrated.db"
    monkeypatch.setenv("ATLAS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()  # env.py resolves the URL through the lru_cached settings
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        get_settings.cache_clear()  # don't leak the temp URL into other tests

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], f"Models and migrations have drifted:\n{diff}"


def test_every_migration_downgrades_and_reapplies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """upgrade head -> downgrade base -> upgrade head on a fresh DB.

    A broken downgrade() is otherwise only discovered mid-rollback. Ending on a
    second upgrade also catches a downgrade that leaves residue (an index or
    table it forgot to drop) which would make the re-upgrade collide, and a
    final drift check catches residue that survives the re-upgrade silently.
    """
    db_path = tmp_path / "roundtrip.db"
    monkeypatch.setenv("ATLAS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            revision = context.get_current_revision()
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()
    assert revision == ScriptDirectory.from_config(config).get_current_head()
    assert diff == [], f"Schema drifted after downgrade/re-upgrade:\n{diff}"
