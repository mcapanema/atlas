from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.snapshots.entities import ForecastSnapshot, MetricSnapshot
from app.infrastructure.repositories.snapshots import (
    SqlAlchemyForecastSnapshotRepository,
    SqlAlchemyMetricSnapshotRepository,
)

TEAM = uuid4()


def _metric(
    captured_on: date, team_id: UUID | None = TEAM, project_id: UUID | None = None
) -> MetricSnapshot:
    return MetricSnapshot(
        captured_on=captured_on,
        window_days=30,
        completed=4,
        wip=2,
        lead_time_p50_seconds=172800.0,
        lead_time_p85_seconds=345600.0,
        cycle_time_p50_seconds=None,
        cycle_time_p85_seconds=None,
        blocked_seconds=0.0,
        flow_efficiency=None,
        team_id=team_id,
        project_id=project_id,
    )


async def test_metric_snapshot_roundtrip_ordered_by_captured_on(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyMetricSnapshotRepository(session)
    await repo.add(_metric(date(2026, 7, 11)))
    await repo.add(_metric(date(2026, 7, 9)))
    await repo.add(_metric(date(2026, 7, 10), team_id=uuid4()))  # other scope

    snapshots = await repo.list(team_id=TEAM)

    assert [s.captured_on for s in snapshots] == [date(2026, 7, 9), date(2026, 7, 11)]
    assert snapshots[0].lead_time_p50_seconds == 172800.0
    assert snapshots[0].cycle_time_p50_seconds is None
    assert snapshots[0].created_at.tzinfo is not None


async def test_metric_snapshot_exists_on(session: AsyncSession) -> None:
    repo = SqlAlchemyMetricSnapshotRepository(session)
    await repo.add(_metric(date(2026, 7, 11)))

    assert await repo.exists_on(date(2026, 7, 11), team_id=TEAM)
    assert not await repo.exists_on(date(2026, 7, 12), team_id=TEAM)
    assert not await repo.exists_on(date(2026, 7, 11), team_id=uuid4())


async def test_metric_snapshot_rejects_duplicate_team_day_at_db_level(
    session: AsyncSession,
) -> None:
    """DB-level guard behind the app-level exists_on check (concurrent syncs)."""
    repo = SqlAlchemyMetricSnapshotRepository(session)
    await repo.add(_metric(date(2026, 7, 11), team_id=TEAM))

    with pytest.raises(IntegrityError):
        await repo.add(_metric(date(2026, 7, 11), team_id=TEAM))


async def test_forecast_snapshot_rejects_duplicate_team_day_at_db_level(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyForecastSnapshotRepository(session)
    team = uuid4()
    await repo.add(
        ForecastSnapshot(
            captured_on=date(2026, 7, 11),
            window_days=90,
            remaining=12,
            p50_days=10,
            p85_days=19,
            team_id=team,
        )
    )

    with pytest.raises(IntegrityError):
        await repo.add(
            ForecastSnapshot(
                captured_on=date(2026, 7, 11),
                window_days=90,
                remaining=5,
                p50_days=3,
                p85_days=8,
                team_id=team,
            )
        )


async def test_forecast_snapshot_roundtrip(session: AsyncSession) -> None:
    repo = SqlAlchemyForecastSnapshotRepository(session)
    project = uuid4()
    await repo.add(
        ForecastSnapshot(
            captured_on=date(2026, 7, 11),
            window_days=90,
            remaining=12,
            p50_days=10,
            p85_days=19,
            project_id=project,
            created_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
        )
    )

    snapshots = await repo.list(project_id=project)

    assert len(snapshots) == 1
    assert snapshots[0].remaining == 12
    assert snapshots[0].p85_days == 19
    assert snapshots[0].team_id is None
    assert await repo.exists_on(date(2026, 7, 11), project_id=project)
