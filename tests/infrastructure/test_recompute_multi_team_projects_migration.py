import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text

from app.config import get_settings

AT = "2026-10-01 00:00:00"


def _team(connection: Connection, org: UUID) -> UUID:
    team = uuid4()
    connection.execute(
        text(
            "INSERT INTO teams (id, organization_id, name, created_at) VALUES (:id, :org, 'T', :at)"
        ),
        {"id": team.hex, "org": org.hex, "at": AT},
    )
    return team


def _project_with_items(connection: Connection, home: UUID, item_teams: list[UUID]) -> None:
    project = uuid4()
    connection.execute(
        text("INSERT INTO projects (id, team_id, name, created_at) VALUES (:id, :t, 'P', :at)"),
        {"id": project.hex, "t": home.hex, "at": AT},
    )
    for team in item_teams:
        connection.execute(
            text(
                "INSERT INTO work_items (id, team_id, project_id, title, type, state, created_at,"
                " labels) VALUES (:id, :t, :p, 'I', 'task', 'Todo', :at, '[]')"
            ),
            {"id": uuid4().hex, "t": team.hex, "p": project.hex, "at": AT},
        )


def test_multi_team_projects_mark_only_their_organization_for_recompute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A multi-team project now reads the workspace rules, so its organization's
    history is recomputed; an organization with only single-team projects isn't."""
    db_path = tmp_path / "multi-team.db"
    monkeypatch.setenv("ATLAS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    o1, o2 = uuid4(), uuid4()
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        command.upgrade(config, "8b2d5f6a1c47")
        with engine.begin() as connection:
            for org in (o1, o2):
                connection.execute(
                    text("INSERT INTO organizations (id, name, created_at) VALUES (:id, 'O', :at)"),
                    {"id": org.hex, "at": AT},
                )
            a, b = _team(connection, o1), _team(connection, o1)
            c = _team(connection, o2)
            _project_with_items(connection, a, [a, b])
            _project_with_items(connection, c, [c, c])
            connection.execute(
                text(
                    "INSERT INTO metric_rule_overrides (id, organization_id, team_id, overrides,"
                    " recompute_state, updated_at) VALUES (:id, :org, NULL, :ov, 'idle', :at)"
                ),
                {"id": uuid4().hex, "org": o2.hex, "ov": json.dumps({"healthy_min": 75}), "at": AT},
            )
        # Its own revision: a later recompute migration marks every organization.
        command.upgrade(config, "c4e8a2b7d913")
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

    assert rows == {o1: ("running", {}), o2: ("idle", {"healthy_min": 75})}
