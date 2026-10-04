"""Capture and serve persisted analytics snapshots.

Snapshots are one row per scope (each team, each project) per UTC day,
captured after sync. Metric snapshots feed dashboard history; forecast
snapshots feed forecast-accuracy calibration. They are re-derived as of
their instant and rewritten in place when a scope's metric rules change
(docs/adr/0010-per-team-metric-rules.md).
"""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

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

        ponytail: the rewrite holds SQLite's write lock from the first
        update() flush through every forecast Monte Carlo until commit; a
        concurrent sync can push it past the busy timeout, so the org goes to
        "failed" and Retry recovers. Upgrade path: compute all values first,
        then write them in one burst.
        """
        data = await self._metrics.load_scope_data(team_id=team_id, project_id=project_id)
        metric_snapshots = await self._metric_snapshots.list(team_id=team_id, project_id=project_id)
        for metric in metric_snapshots:
            scope = data.samples(as_of=metric.created_at)
            values = await self._metric_values(scope, metric.created_at)
            await self._metric_snapshots.update(replace(metric, **values))
        forecast_snapshots = await self._forecast_snapshots.list(
            team_id=team_id, project_id=project_id
        )
        for forecast in forecast_snapshots:
            scope = data.samples(as_of=forecast.created_at)
            values = await self._forecast_values(scope, forecast.created_at)
            await self._forecast_snapshots.update(replace(forecast, **values))
        return len(metric_snapshots) + len(forecast_snapshots)

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
            MetricSnapshot(
                captured_on=today,
                team_id=team_id,
                project_id=project_id,
                created_at=at,
                **await self._metric_values(scope, at),
            )
        )
        await self._forecast_snapshots.add(
            ForecastSnapshot(
                captured_on=today,
                team_id=team_id,
                project_id=project_id,
                created_at=at,
                **await self._forecast_values(scope, at),
            )
        )
        return 1

    async def _metric_values(self, scope: ScopeSamples, at: datetime) -> dict[str, Any]:
        metrics = await self._metrics.get_flow_metrics(
            window_days=METRICS_WINDOW_DAYS, now=at, scope=scope
        )
        lead, cycle = metrics.lead_time, metrics.cycle_time
        return {
            "window_days": METRICS_WINDOW_DAYS,
            "completed": metrics.completed,
            "wip": metrics.wip,
            "lead_time_p50_seconds": lead.p50.total_seconds() if lead else None,
            "lead_time_p85_seconds": lead.p85.total_seconds() if lead else None,
            "cycle_time_p50_seconds": cycle.p50.total_seconds() if cycle else None,
            "cycle_time_p85_seconds": cycle.p85.total_seconds() if cycle else None,
            "blocked_seconds": metrics.blocked_time.total_seconds(),
            "flow_efficiency": metrics.flow_efficiency,
        }

    async def _forecast_values(self, scope: ScopeSamples, at: datetime) -> dict[str, Any]:
        forecast = await self._forecasts.get_forecast(now=at, scope=scope)
        completion = forecast.completion
        return {
            "window_days": scope.rules.forecast_history_days,
            "remaining": forecast.remaining,
            "p50_days": completion.p50_days if completion else None,
            "p85_days": completion.p85_days if completion else None,
        }
