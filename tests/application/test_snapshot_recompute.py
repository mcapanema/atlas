from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.application.forecasting.service import ForecastService
from app.application.metric_rules.resolver import MetricRulesResolver
from app.application.metrics.service import MetricsService
from app.application.snapshots.service import SnapshotService
from app.domain.events.entities import Event, EventType
from app.domain.forecasting.monte_carlo import DeliveryForecast
from app.domain.metric_rules.entities import DEFAULT_RULES, RuleOverrides
from app.domain.metrics.summary import FlowMetrics
from app.domain.snapshots.entities import ForecastSnapshot, MetricSnapshot
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from tests.fakes import (
    InMemoryEventRepository,
    InMemoryForecastSnapshotRepository,
    InMemoryMetricRuleOverridesRepository,
    InMemoryMetricSnapshotRepository,
    InMemoryProjectRepository,
    InMemoryTeamRepository,
    InMemoryWorkItemRepository,
)

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
ORG = uuid4()


def _at(item: WorkItem, type_: EventType, days_ago: int) -> Event:
    return Event(work_item_id=item.id, type=type_, occurred_at=NOW - timedelta(days=days_ago))


def _service(
    team: Team,
    items: Sequence[WorkItem],
    events: Sequence[Event],
    overrides: InMemoryMetricRuleOverridesRepository,
) -> tuple[SnapshotService, InMemoryMetricSnapshotRepository, InMemoryForecastSnapshotRepository]:
    work_items = InMemoryWorkItemRepository(list(items))
    event_repo = InMemoryEventRepository(list(events))
    teams = InMemoryTeamRepository([team])
    projects = InMemoryProjectRepository()
    resolver = MetricRulesResolver(overrides, teams, projects)
    metric_snapshots = InMemoryMetricSnapshotRepository()
    forecast_snapshots = InMemoryForecastSnapshotRepository()
    service = SnapshotService(
        MetricsService(work_items, event_repo, resolver),
        ForecastService(work_items, event_repo, resolver),
        teams,
        projects,
        metric_snapshots,
        forecast_snapshots,
    )
    return service, metric_snapshots, forecast_snapshots


async def test_recompute_rewrites_history_in_place_under_new_rules() -> None:
    team = Team(organization_id=ORG, name="Platform")
    item = WorkItem(team_id=team.id, title="Parked then restarted")
    events = [
        _at(item, EventType.CREATED, 20),
        _at(item, EventType.STARTED, 18),
        _at(item, EventType.STOPPED, 15),
        _at(item, EventType.STARTED, 4),
        _at(item, EventType.COMPLETED, 2),
    ]
    overrides = InMemoryMetricRuleOverridesRepository()
    service, metric_snapshots, _ = _service(team, [item], events, overrides)
    await service.capture_all(now=NOW)
    (before,) = await metric_snapshots.list(team_id=team.id)
    assert before.cycle_time_p50_seconds == timedelta(days=16).total_seconds()

    await overrides.save(
        RuleOverrides(
            organization_id=ORG,
            team_id=team.id,
            overrides={"restart_clock_after_move_back": True},
        )
    )
    rewritten = await service.recompute_scope(team_id=team.id)

    (after,) = await metric_snapshots.list(team_id=team.id)
    assert rewritten == 2  # one metric + one forecast snapshot
    assert after.cycle_time_p50_seconds == timedelta(days=2).total_seconds()
    assert (after.id, after.captured_on, after.created_at) == (
        before.id,
        before.captured_on,
        before.created_at,
    )


async def test_capture_and_recompute_see_each_snapshot_as_of_its_instant() -> None:
    team = Team(organization_id=ORG, name="Platform")
    item = WorkItem(team_id=team.id, title="Finished later")
    events = [
        _at(item, EventType.CREATED, 20),
        _at(item, EventType.STARTED, 15),
        _at(item, EventType.COMPLETED, 2),
    ]
    service, metric_snapshots, forecast_snapshots = _service(
        team, [item], events, InMemoryMetricRuleOverridesRepository()
    )
    await service.capture_all(now=NOW - timedelta(days=10))
    await service.capture_all(now=NOW)

    await service.recompute_scope(team_id=team.id)

    old_forecast, new_forecast = await forecast_snapshots.list(team_id=team.id)
    assert (old_forecast.remaining, new_forecast.remaining) == (1, 0)
    old_metrics, new_metrics = await metric_snapshots.list(team_id=team.id)
    assert (old_metrics.wip, old_metrics.completed) == (1, 0)
    assert (new_metrics.wip, new_metrics.completed) == (0, 1)


async def test_recompute_rewrites_a_forecast_with_the_teams_history_window() -> None:
    team = Team(organization_id=ORG, name="Platform")
    done = WorkItem(team_id=team.id, title="Finished long ago")
    open_item = WorkItem(team_id=team.id, title="Still open")
    events = [
        _at(done, EventType.CREATED, 80),
        _at(done, EventType.COMPLETED, 60),
        _at(open_item, EventType.CREATED, 70),
    ]
    overrides = InMemoryMetricRuleOverridesRepository()
    service, _, forecast_snapshots = _service(team, [done, open_item], events, overrides)
    await service.capture_all(now=NOW)
    (before,) = await forecast_snapshots.list(team_id=team.id)
    assert before.window_days == DEFAULT_RULES.forecast_history_days
    assert before.p50_days is not None  # the 60-day-old completion is inside 90 days

    await overrides.save(
        RuleOverrides(organization_id=ORG, team_id=team.id, overrides={"forecast_history_days": 30})
    )
    await service.recompute_scope(team_id=team.id)

    (after,) = await forecast_snapshots.list(team_id=team.id)
    assert after.window_days == 30
    assert after.p50_days is None  # ...and outside 30: nothing left to simulate from
    assert after.id == before.id


class _RecordingMetricSnapshots(InMemoryMetricSnapshotRepository):
    log: list[str]

    async def update(self, snapshot: MetricSnapshot) -> None:
        self.log.append("update")
        await super().update(snapshot)


class _RecordingForecastSnapshots(InMemoryForecastSnapshotRepository):
    log: list[str]

    async def update(self, snapshot: ForecastSnapshot) -> None:
        self.log.append("update")
        await super().update(snapshot)


class _RecordingMetrics(MetricsService):
    log: list[str]

    async def get_flow_metrics(self, **kwargs: Any) -> FlowMetrics:
        self.log.append("compute")
        return await super().get_flow_metrics(**kwargs)


class _RecordingForecasts(ForecastService):
    log: list[str]

    async def get_forecast(self, **kwargs: Any) -> DeliveryForecast:
        self.log.append("compute")
        return await super().get_forecast(**kwargs)


async def test_recompute_computes_every_value_before_the_first_write() -> None:
    team = Team(organization_id=ORG, name="Platform")
    item = WorkItem(team_id=team.id, title="Finished")
    events = [_at(item, EventType.CREATED, 20), _at(item, EventType.COMPLETED, 2)]
    log: list[str] = []
    work_items = InMemoryWorkItemRepository([item])
    event_repo = InMemoryEventRepository(events)
    teams = InMemoryTeamRepository([team])
    projects = InMemoryProjectRepository()
    resolver = MetricRulesResolver(InMemoryMetricRuleOverridesRepository(), teams, projects)
    metrics = _RecordingMetrics(work_items, event_repo, resolver)
    forecasts = _RecordingForecasts(work_items, event_repo, resolver)
    metric_snapshots = _RecordingMetricSnapshots()
    forecast_snapshots = _RecordingForecastSnapshots()
    for recorder in (metrics, forecasts, metric_snapshots, forecast_snapshots):
        recorder.log = log
    service = SnapshotService(
        metrics, forecasts, teams, projects, metric_snapshots, forecast_snapshots
    )
    await service.capture_all(now=NOW - timedelta(days=1))
    await service.capture_all(now=NOW)
    log.clear()

    await service.recompute_scope(team_id=team.id)

    assert log == ["compute"] * 4 + ["update"] * 4
