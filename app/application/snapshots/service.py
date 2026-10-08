"""Capture and serve persisted analytics snapshots.

Snapshots are one row per scope (each team, each project) per UTC day,
captured after sync. Metric snapshots feed dashboard history; forecast
snapshots feed forecast-accuracy calibration. They are re-derived as of
their instant and rewritten in place when a scope's metric rules change
(docs/adr/0010-per-team-metric-rules.md).
"""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from app.application.forecasting.service import ForecastService
from app.application.metrics.service import MetricsService
from app.application.scope import ScopeSamples
from app.domain.forecasting.accuracy import (
    ForecastAccuracy,
    evaluate_forecast_accuracy,
)
from app.domain.projects.repository import ProjectRepository
from app.domain.snapshots.entities import ForecastSnapshot, MetricSnapshot
from app.domain.snapshots.repository import (
    ForecastSnapshotRepository,
    MetricSnapshotRepository,
)
from app.domain.teams.repository import TeamRepository

METRICS_WINDOW_DAYS = 30


class SnapshotService:
    """Application use cases for analytics snapshots."""

    def __init__(
        self,
        metrics: MetricsService,
        forecasts: ForecastService,
        teams: TeamRepository,
        projects: ProjectRepository,
        metric_snapshots: MetricSnapshotRepository,
        forecast_snapshots: ForecastSnapshotRepository,
    ) -> None:
        self._metrics = metrics
        self._forecasts = forecasts
        self._teams = teams
        self._projects = projects
        self._metric_snapshots = metric_snapshots
        self._forecast_snapshots = forecast_snapshots

    async def capture_all(self, *, now: datetime | None = None) -> int:
        """Snapshot every team and project scope; returns scopes captured.

        Idempotent per UTC day — a scope already captured today is skipped,
        so re-syncing is a no-op here too.

        ponytail: runs one Monte Carlo forecast (~1s, off-thread) per team
        plus per project on every sync, so added sync latency scales
        linearly with team count + project count — fine for today's
        workspace sizes. Once that's slow enough to matter, move capture to
        a background task after the sync response, or batch/reuse forecasts
        instead of re-simulating per scope.
        """
        at = now if now is not None else datetime.now(UTC)
        captured = 0
        for team in await self._teams.list():
            captured += await self._capture(at, team_id=team.id)
        for project in await self._projects.list():
            captured += await self._capture(at, project_id=project.id)
        return captured

    async def capture_team(self, team_id: UUID, *, now: datetime | None = None) -> int:
        """Snapshot one team and its projects; returns scopes captured.

        For a team sync: every other scope is still stale, and capturing it
        now would freeze today's point from that stale data (idempotent per
        day, so the organization sync later today would skip it).
        """
        at = now if now is not None else datetime.now(UTC)
        captured = await self._capture(at, team_id=team_id)
        for project in await self._projects.list():
            if project.team_id == team_id:
                captured += await self._capture(at, project_id=project.id)
        return captured

    async def get_metric_history(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[MetricSnapshot]:
        """The scope's metric snapshots, oldest first."""
        return await self._metric_snapshots.list(team_id=team_id, project_id=project_id)

    async def get_forecast_accuracy(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> ForecastAccuracy:
        """Calibration of the scope's past forecasts against actual completions."""
        snapshots = await self._forecast_snapshots.list(team_id=team_id, project_id=project_id)
        scope = await self._metrics.load_scope(team_id=team_id, project_id=project_id)
        completions = [s.completed_at for s in scope.samples if s.completed_at is not None]
        return evaluate_forecast_accuracy(snapshots, completions)

    async def recompute_scope(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int:
        """Rewrite the scope's snapshot history under its current metric rules.

        Each snapshot is re-derived as of its original capture instant
        (`created_at`): streams are truncated there, so later events (a
        reopen, a backfill) don't leak into the past. Forecast snapshots
        become a backtest of the current rules. Rows keep their id, day and
        instant. Returns the number of snapshots rewritten.

        Every new value is computed first (reads only, forecasts included),
        then all updates are issued in one burst; the caller commits once.

        ponytail: the write lock is held for that burst plus the commit, once
        per scope; a concurrent sync can still push past the SQLite busy
        timeout, so the org goes to "failed" and Retry recovers. Upgrade
        path: PostgreSQL. Shorter per-snapshot transactions would trade the
        recompute runner's invariant (a cancel or failure never leaves a
        scope half old, half new) for lock time, so they are not the path.
        """
        data = await self._metrics.load_scope_data(team_id=team_id, project_id=project_id)
        old_metrics = await self._metric_snapshots.list(team_id=team_id, project_id=project_id)
        old_forecasts = await self._forecast_snapshots.list(team_id=team_id, project_id=project_id)
        metrics = [
            await self._metric_snapshot(
                data.samples(as_of=m.created_at),
                m.created_at,
                m.captured_on,
                m.id,
                team_id,
                project_id,
            )
            for m in old_metrics
        ]
        forecasts = [
            await self._forecast_snapshot(
                data.samples(as_of=f.created_at),
                f.created_at,
                f.captured_on,
                f.id,
                team_id,
                project_id,
            )
            for f in old_forecasts
        ]
        for metric in metrics:
            await self._metric_snapshots.update(metric)
        for forecast in forecasts:
            await self._forecast_snapshots.update(forecast)
        return len(metrics) + len(forecasts)

    async def _capture(
        self,
        at: datetime,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> int:
        today = at.date()
        if await self._metric_snapshots.exists_on(today, team_id=team_id, project_id=project_id):
            return 0
        data = await self._metrics.load_scope_data(team_id=team_id, project_id=project_id)
        scope = data.samples(as_of=at)
        await self._metric_snapshots.add(
            await self._metric_snapshot(scope, at, today, uuid4(), team_id, project_id)
        )
        await self._forecast_snapshots.add(
            await self._forecast_snapshot(scope, at, today, uuid4(), team_id, project_id)
        )
        return 1

    async def _metric_snapshot(
        self,
        scope: ScopeSamples,
        at: datetime,
        captured_on: date,
        snapshot_id: UUID,
        team_id: UUID | None,
        project_id: UUID | None,
    ) -> MetricSnapshot:
        metrics = await self._metrics.get_flow_metrics(
            window_days=METRICS_WINDOW_DAYS, now=at, scope=scope
        )
        lead, cycle = metrics.lead_time, metrics.cycle_time
        return MetricSnapshot(
            id=snapshot_id,
            captured_on=captured_on,
            team_id=team_id,
            project_id=project_id,
            created_at=at,
            window_days=METRICS_WINDOW_DAYS,
            completed=metrics.completed,
            wip=metrics.wip,
            lead_time_p50_seconds=lead.p50.total_seconds() if lead else None,
            lead_time_p85_seconds=lead.p85.total_seconds() if lead else None,
            cycle_time_p50_seconds=cycle.p50.total_seconds() if cycle else None,
            cycle_time_p85_seconds=cycle.p85.total_seconds() if cycle else None,
            blocked_seconds=metrics.blocked_time.total_seconds(),
            flow_efficiency=metrics.flow_efficiency,
        )

    async def _forecast_snapshot(
        self,
        scope: ScopeSamples,
        at: datetime,
        captured_on: date,
        snapshot_id: UUID,
        team_id: UUID | None,
        project_id: UUID | None,
    ) -> ForecastSnapshot:
        forecast = await self._forecasts.get_forecast(now=at, scope=scope)
        completion = forecast.completion
        return ForecastSnapshot(
            id=snapshot_id,
            captured_on=captured_on,
            team_id=team_id,
            project_id=project_id,
            created_at=at,
            window_days=scope.rules.forecast_history_days,
            remaining=forecast.remaining,
            p50_days=completion.p50_days if completion else None,
            p85_days=completion.p85_days if completion else None,
        )
