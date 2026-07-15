from collections.abc import Set as AbstractSet
from datetime import UTC, datetime
from uuid import UUID

from app.application.scope import ScopeSampleLoader, ScopeSamples
from app.domain.events.repository import EventRepository
from app.domain.metrics.aging import AgingWip, compute_aging_wip
from app.domain.metrics.distribution import (
    LeadTimeDistribution,
    compute_lead_time_distribution,
)
from app.domain.metrics.health import DeliveryHealth, compute_delivery_health
from app.domain.metrics.history import FlowHistory, compute_flow_history
from app.domain.metrics.summary import FlowMetrics, compute_flow_metrics
from app.domain.work_items.entities import WorkItemType
from app.domain.work_items.repository import WorkItemRepository


class MetricsService:
    """Application use cases for flow metrics."""

    def __init__(self, work_items: WorkItemRepository, events: EventRepository) -> None:
        self._scope = ScopeSampleLoader(work_items, events)

    async def load_scope(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        types: AbstractSet[WorkItemType] | None = None,
        exclude_states: AbstractSet[str] | None = None,
    ) -> ScopeSamples:
        """One scope load, shareable across the analytics calls via `scope=`."""
        return await self._scope.load(
            team_id=team_id,
            project_id=project_id,
            types=types,
            exclude_states=exclude_states,
        )

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

    async def get_aging_wip(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> AgingWip:
        """Ages of the scope's current in-progress items, oldest first."""
        at = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_aging_wip(scope.items_with_samples, now=at)

    async def get_delivery_health(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 30,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> DeliveryHealth:
        """Composite delivery-health score over the trailing window ending at `now`."""
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_delivery_health(scope.streams, now=window_end, window_days=window_days)
