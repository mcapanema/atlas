from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.forecasting.service import ForecastService
from app.application.metrics.service import MetricsService
from app.application.snapshots.service import (
    FORECAST_WINDOW_DAYS,
    METRICS_WINDOW_DAYS,
    SnapshotService,
)
from app.domain.events.entities import Event, EventType
from app.domain.projects.entities import Project
from app.domain.snapshots.entities import ForecastSnapshot
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from tests.fakes import (
    InMemoryEventRepository,
    InMemoryForecastSnapshotRepository,
    InMemoryMetricSnapshotRepository,
    InMemoryProjectRepository,
    InMemoryTeamRepository,
    InMemoryWorkItemRepository,
)

NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _harness() -> tuple[
    SnapshotService,
    InMemoryMetricSnapshotRepository,
    InMemoryForecastSnapshotRepository,
    Team,
]:
    team = Team(organization_id=uuid4(), name="Platform")
    project = Project(team_id=team.id, name="Q3 Launch")
    done = WorkItem(team_id=team.id, title="Done item", project_id=project.id)
    open_item = WorkItem(team_id=team.id, title="Open item", project_id=project.id)
    events = [
        Event(
            work_item_id=done.id,
            type=EventType.CREATED,
            occurred_at=NOW - timedelta(days=10),
        ),
        Event(
            work_item_id=done.id,
            type=EventType.STARTED,
            occurred_at=NOW - timedelta(days=8),
        ),
        Event(
            work_item_id=done.id,
            type=EventType.COMPLETED,
            occurred_at=NOW - timedelta(days=2),
        ),
        Event(
            work_item_id=open_item.id,
            type=EventType.CREATED,
            occurred_at=NOW - timedelta(days=5),
        ),
    ]
    work_items = InMemoryWorkItemRepository([done, open_item])
    event_repo = InMemoryEventRepository(events)
    metric_snapshots = InMemoryMetricSnapshotRepository()
    forecast_snapshots = InMemoryForecastSnapshotRepository()
    service = SnapshotService(
        MetricsService(work_items, event_repo),
        ForecastService(work_items, event_repo),
        InMemoryTeamRepository([team]),
        InMemoryProjectRepository([project]),
        metric_snapshots,
        forecast_snapshots,
    )
    return service, metric_snapshots, forecast_snapshots, team


async def test_capture_all_snapshots_every_team_and_project_scope() -> None:
    service, metric_snapshots, forecast_snapshots, team = _harness()

    captured = await service.capture_all(now=NOW)

    assert captured == 2  # one team scope + one project scope
    team_metrics = await metric_snapshots.list(team_id=team.id)
    assert len(team_metrics) == 1
    assert team_metrics[0].captured_on == NOW.date()
    assert team_metrics[0].window_days == METRICS_WINDOW_DAYS
    assert team_metrics[0].completed == 1
    assert team_metrics[0].wip == 0
    assert team_metrics[0].lead_time_p50_seconds == timedelta(days=8).total_seconds()
    team_forecasts = await forecast_snapshots.list(team_id=team.id)
    assert len(team_forecasts) == 1
    assert team_forecasts[0].window_days == FORECAST_WINDOW_DAYS
    assert team_forecasts[0].remaining == 1
    assert team_forecasts[0].p50_days is not None


async def test_capture_all_is_idempotent_per_day() -> None:
    service, metric_snapshots, _, team = _harness()

    await service.capture_all(now=NOW)
    captured_again = await service.capture_all(now=NOW + timedelta(hours=3))

    assert captured_again == 0
    assert len(await metric_snapshots.list(team_id=team.id)) == 1


async def test_capture_all_captures_again_next_day() -> None:
    service, metric_snapshots, _, team = _harness()

    await service.capture_all(now=NOW)
    captured = await service.capture_all(now=NOW + timedelta(days=1))

    assert captured == 2
    assert len(await metric_snapshots.list(team_id=team.id)) == 2


async def test_get_metric_history_returns_scope_snapshots() -> None:
    service, _, _, team = _harness()
    await service.capture_all(now=NOW)

    history = await service.get_metric_history(team_id=team.id)

    assert [s.captured_on for s in history] == [NOW.date()]


async def test_get_forecast_accuracy_evaluates_resolved_past_forecasts() -> None:
    service, _, forecast_snapshots, team = _harness()
    # A week-old forecast: 1 remaining, P50 5d / P85 10d. The completion
    # 2 days before NOW resolved it in 5 days — a hit on both percentiles.
    await forecast_snapshots.add(
        ForecastSnapshot(
            captured_on=(NOW - timedelta(days=7)).date(),
            window_days=FORECAST_WINDOW_DAYS,
            remaining=1,
            p50_days=5,
            p85_days=10,
            team_id=team.id,
            created_at=NOW - timedelta(days=7),
        )
    )

    accuracy = await service.get_forecast_accuracy(team_id=team.id)

    assert accuracy.evaluated == 1
    assert accuracy.pending == 0
    assert accuracy.p50_hit_rate == 1.0
    assert accuracy.p85_hit_rate == 1.0
