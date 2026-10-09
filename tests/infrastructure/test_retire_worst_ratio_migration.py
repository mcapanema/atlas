import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings


def test_retiring_the_worst_ratio_drops_only_that_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0016 retired predictability_worst_ratio. The write schema forbids
    unknown keys, so a stored override could never be cleared and logged a
    warning on every scope load: the migration removes it, nothing else."""
    db_path = tmp_path / "retire-worst-ratio.db"
    monkeypatch.setenv("ATLAS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    config = Config("alembic.ini")
    org = uuid4()
    stored = {
        "tuned": {"predictability_worst_ratio": 3.0, "aging_percentile": 80},
        "untouched": {"healthy_min": 75},
    }
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        command.upgrade(config, "5b3beedabfc0")
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO organizations (id, name, created_at) VALUES (:id, 'O', :at)"),
                {"id": org.hex, "at": "2026-10-01 00:00:00"},
            )
            for name, overrides in stored.items():
                team = uuid4()
                connection.execute(
                    text(
                        "INSERT INTO teams (id, organization_id, name, created_at)"
                        " VALUES (:id, :org, :name, :at)"
                    ),
                    {"id": team.hex, "org": org.hex, "name": name, "at": "2026-10-01 00:00:00"},
                )
                connection.execute(
                    text(
                        "INSERT INTO metric_rule_overrides (id, organization_id, team_id,"
                        " overrides, recompute_state, updated_at)"
                        " VALUES (:id, :org, :team, :overrides, 'idle', :at)"
                    ),
                    {
                        "id": uuid4().hex,
                        "org": org.hex,
                        "team": team.hex,
                        "overrides": json.dumps(overrides),
                        "at": "2026-10-01 00:00:00",
                    },
                )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT teams.name, metric_rule_overrides.overrides FROM metric_rule_overrides"
                    " JOIN teams ON teams.id = metric_rule_overrides.team_id"
                )
            ).all()
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert {name: json.loads(overrides) for name, overrides in rows} == {
        "tuned": {"aging_percentile": 80},
        "untouched": {"healthy_min": 75},
    }
