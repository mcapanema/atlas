from datetime import UTC, datetime
from uuid import UUID

from app.application.scope import ScopeSampleLoader, ScopeSamples
from app.domain.events.repository import EventRepository
from app.domain.metrics.distribution import (
    LeadTimeDistribution,
    compute_lead_time_distribution,
)
from app.domain.metrics.history import FlowHistory, compute_flow_history
from app.domain.metrics.summary import FlowMetrics, compute_flow_metrics
from app.domain.work_items.repository import WorkItemRepository


class MetricsService:
    """Application use cases for flow metrics."""

    def __init__(self, work_items: WorkItemRepository, events: EventRepository) -> None:
        self._scope = ScopeSampleLoader(work_items, events)

    async def load_scope(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> ScopeSamples:
        """One scope load, shareable across the analytics calls via `scope=`."""
        return await self._scope.load(team_id=team_id, project_id=project_id)

    async def get_flow_metrics(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 30,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> FlowMetrics:
        """Compute the scope's flow metrics over the trailing window ending at `now`."""
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_flow_metrics(scope.samples, now=window_end, window_days=window_days)

    async def get_flow_history(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 90,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> FlowHistory:
        """Compute the scope's chart time series over the trailing window."""
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_flow_history(scope.streams, now=window_end, window_days=window_days)

    async def get_lead_time_distribution(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 90,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> LeadTimeDistribution:
        """Histogram of lead times for scope items completed in the trailing window."""
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_lead_time_distribution(
            scope.samples, now=window_end, window_days=window_days
        )
