import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings

AT = "2026-10-01 00:00:00"
BEFORE = "8e8cbbb28dcd"


def test_every_organization_is_marked_for_recompute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0025 changed the blocked defaults, so every organization's history
    is recomputed; an organization without an overrides row gets an empty one."""
    db_path = tmp_path / "explicit-blocked.db"
    monkeypatch.setenv("ATLAS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    with_row, without_row = uuid4(), uuid4()
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        command.upgrade(config, BEFORE)
        with engine.begin() as connection:
            for org in (with_row, without_row):
                connection.execute(
                    text("INSERT INTO organizations (id, name, created_at) VALUES (:id, 'O', :at)"),
                    {"id": org.hex, "at": AT},
                )
            connection.execute(
                text(
                    "INSERT INTO metric_rule_overrides (id, organization_id, team_id, overrides,"
                    " recompute_state, updated_at) VALUES (:id, :org, NULL, :ov, 'idle', :at)"
                ),
                {
                    "id": uuid4().hex,
                    "org": with_row.hex,
                    "ov": json.dumps({"timezone": "America/Sao_Paulo"}),
                    "at": AT,
                },
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            rows = {
                UUID(org): (state, json.loads(overrides))
                for org, state, overrides in connection.execute(
                    text(
                        "SELECT organization_id, recompute_state, overrides"
                        " FROM metric_rule_overrides WHERE team_id IS NULL"
                    )
                )
            }
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert rows == {
        with_row: ("running", {"timezone": "America/Sao_Paulo"}),
        without_row: ("running", {}),
    }
