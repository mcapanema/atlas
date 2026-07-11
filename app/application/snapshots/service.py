"""Capture and serve persisted analytics snapshots.

Snapshots are the SPEC's historical-aggregation concept: one immutable row
per scope (each team, each project) per UTC day, captured after sync.
Metric snapshots feed dashboard history; forecast snapshots feed
forecast-accuracy calibration. The compute-on-read analytics stay the
live source — snapshots are a write-side record of what they said.
"""

from datetime import UTC, datetime
from uuid import UUID

from app.application.forecasting.service import ForecastService
from app.application.metrics.service import MetricsService
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
FORECAST_WINDOW_DAYS = 90


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
        snapshots = await self._forecast_snapshots.list(
            team_id=team_id, project_id=project_id
        )
        scope = await self._metrics.load_scope(team_id=team_id, project_id=project_id)
        completions = [
            s.completed_at for s in scope.samples if s.completed_at is not None
        ]
        return evaluate_forecast_accuracy(snapshots, completions)

    async def _capture(
        self,
        at: datetime,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> int:
        today = at.date()
        if await self._metric_snapshots.exists_on(
            today, team_id=team_id, project_id=project_id
        ):
            return 0
        scope = await self._metrics.load_scope(team_id=team_id, project_id=project_id)
        metrics = await self._metrics.get_flow_metrics(
            window_days=METRICS_WINDOW_DAYS, now=at, scope=scope
        )
        forecast = await self._forecasts.get_forecast(
            window_days=FORECAST_WINDOW_DAYS, now=at, scope=scope
        )
        lead, cycle = metrics.lead_time, metrics.cycle_time
        await self._metric_snapshots.add(
            MetricSnapshot(
                captured_on=today,
                window_days=METRICS_WINDOW_DAYS,
                completed=metrics.completed,
                wip=metrics.wip,
                lead_time_p50_seconds=lead.p50.total_seconds() if lead else None,
                lead_time_p85_seconds=lead.p85.total_seconds() if lead else None,
                cycle_time_p50_seconds=cycle.p50.total_seconds() if cycle else None,
                cycle_time_p85_seconds=cycle.p85.total_seconds() if cycle else None,
                blocked_seconds=metrics.blocked_time.total_seconds(),
                flow_efficiency=metrics.flow_efficiency,
                team_id=team_id,
                project_id=project_id,
            )
        )
        completion = forecast.completion
        await self._forecast_snapshots.add(
            ForecastSnapshot(
                captured_on=today,
                window_days=FORECAST_WINDOW_DAYS,
                remaining=forecast.remaining,
                p50_days=completion.p50_days if completion else None,
                p85_days=completion.p85_days if completion else None,
                team_id=team_id,
                project_id=project_id,
            )
        )
        return 1
