from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings


def test_purge_deletes_only_linear_derived_blocked_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sync `def`: migrations/env.py calls asyncio.run()."""
    db_path = tmp_path / "purge.db"
    monkeypatch.setenv("ATLAS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        command.upgrade(config, "28361edf3e47")
        with engine.begin() as connection:
            for external_id in ("i1:h1:blocked", "i1:h1:unblocked", "i1:h2", "manual-note", None):
                connection.execute(
                    text(
                        "INSERT INTO events (id, work_item_id, type, occurred_at, external_id,"
                        " recorded_at) VALUES (:id, :item, 'blocked', '2026-10-01 00:00:00',"
                        " :external_id, '2026-10-01 00:00:00')"
                    ),
                    {"id": uuid4().hex, "item": uuid4().hex, "external_id": external_id},
                )
        command.upgrade(config, "b1c0ed5e0a01")
        with engine.connect() as connection:
            remaining: set[str | None] = set(
                connection.execute(text("SELECT external_id FROM events")).scalars()
            )
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert remaining == {"i1:h2", "manual-note", None}
