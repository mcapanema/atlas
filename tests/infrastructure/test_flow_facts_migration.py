from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings


def test_migration_purges_derived_blocked_events_and_defaults_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sync `def`: migrations/env.py calls asyncio.run()."""
    db_path = tmp_path / "facts.db"
    monkeypatch.setenv("ATLAS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(f"sqlite:///{db_path}")
    item_id = uuid4().hex
    try:
        command.upgrade(config, "c0f1a6e5b2d4")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO work_items (id, team_id, title, type, state, created_at)"
                    " VALUES (:id, :team, 'Fix', 'task', 'Todo', '2026-10-01 00:00:00')"
                ),
                {"id": item_id, "team": uuid4().hex},
            )
            for external_id in ("i1:h1:blocked", "i1:h1:unblocked", "i1:h2", None):
                connection.execute(
                    text(
                        "INSERT INTO events (id, work_item_id, type, occurred_at, external_id,"
                        " recorded_at) VALUES (:id, :item, 'blocked', '2026-10-01 00:00:00',"
                        " :external_id, '2026-10-01 00:00:00')"
                    ),
                    {"id": uuid4().hex, "item": item_id, "external_id": external_id},
                )
        command.upgrade(config, "e5b8d2a7c913")
        with engine.connect() as connection:
            remaining: set[str | None] = set(
                connection.execute(text("SELECT external_id FROM events")).scalars()
            )
            labels: str = connection.execute(text("SELECT labels FROM work_items")).scalar_one()
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert remaining == {"i1:h2", None}
    assert labels == "[]"
