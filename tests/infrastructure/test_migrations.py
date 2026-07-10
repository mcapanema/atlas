from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

import app.infrastructure.repositories  # noqa: F401  # registers ORM models on Base.metadata
from app.config import get_settings
from app.infrastructure.database.base import Base


def test_upgrade_head_matches_orm_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
