from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.snapshots.entities import ForecastSnapshot, MetricSnapshot

TEAM = uuid4()


def _metric_snapshot(
    team_id: UUID | None = TEAM, project_id: UUID | None = None
) -> MetricSnapshot:
    return MetricSnapshot(
        captured_on=date(2026, 7, 11),
        window_days=30,
        completed=4,
        wip=2,
        lead_time_p50_seconds=172800.0,
        lead_time_p85_seconds=345600.0,
        cycle_time_p50_seconds=86400.0,
        cycle_time_p85_seconds=259200.0,
        blocked_seconds=3600.0,
        flow_efficiency=0.9,
        team_id=team_id,
        project_id=project_id,
    )


def test_metric_snapshot_defaults_id_and_created_at() -> None:
    snapshot = _metric_snapshot()

    assert snapshot.id is not None
    assert snapshot.created_at.tzinfo is UTC


def test_metric_snapshot_requires_exactly_one_scope_id() -> None:
    with pytest.raises(ValueError):
        _metric_snapshot(team_id=None)
    with pytest.raises(ValueError):
        _metric_snapshot(project_id=uuid4())


def test_forecast_snapshot_requires_exactly_one_scope_id() -> None:
    snapshot = ForecastSnapshot(
        captured_on=date(2026, 7, 11),
        window_days=90,
        remaining=12,
        p50_days=10,
        p85_days=19,
        project_id=uuid4(),
    )

    assert snapshot.team_id is None
    with pytest.raises(ValueError):
        ForecastSnapshot(
            captured_on=date(2026, 7, 11),
            window_days=90,
            remaining=12,
            p50_days=10,
            p85_days=19,
        )


def test_forecast_snapshot_allows_no_prediction() -> None:
    snapshot = ForecastSnapshot(
        captured_on=date(2026, 7, 11),
        window_days=90,
        remaining=0,
        p50_days=None,
        p85_days=None,
        team_id=uuid4(),
        created_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )

    assert snapshot.p50_days is None
