from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

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


def test_blocked_defaults_migration_schedules_a_history_recompute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0015 changed the built-in blocked rules, so stored snapshot history
    is stale: the migration marks every organization "running", which the
    app's lifespan resumes as a recompute on the next start."""
    db_path = tmp_path / "blocked-defaults.db"
    monkeypatch.setenv("ATLAS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    with_row, without_row = uuid4(), uuid4()
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        command.upgrade(config, "e3aa72adf0b8")
        with engine.begin() as connection:
            for org in (with_row, without_row):
                connection.execute(
                    text("INSERT INTO organizations (id, name, created_at) VALUES (:id, 'O', :at)"),
                    {"id": org.hex, "at": "2026-10-01 00:00:00"},
                )
            connection.execute(
                text(
                    "INSERT INTO metric_rule_overrides (id, organization_id, team_id, overrides,"
                    " recompute_state, updated_at) VALUES (:id, :org, NULL, '{}', 'idle', :at)"
                ),
                {"id": uuid4().hex, "org": with_row.hex, "at": "2026-10-01 00:00:00"},
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT organization_id, recompute_state, recompute_started_at"
                    " FROM metric_rule_overrides WHERE team_id IS NULL"
                )
            ).all()
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert {UUID(org) for org, _, _ in rows} == {with_row, without_row}
    assert all(state == "running" and started for _, state, started in rows)
