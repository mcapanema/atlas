from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from app.domain.events.entities import Event
from app.domain.events.repository import EventRepository
from app.domain.metrics.history import FlowHistory, compute_flow_history
from app.domain.metrics.samples import derive_flow_sample
from app.domain.metrics.summary import FlowMetrics, compute_flow_metrics
from app.domain.work_items.repository import WorkItemRepository


class MetricsService:
    """Application use cases for flow metrics."""

    def __init__(self, work_items: WorkItemRepository, events: EventRepository) -> None:
        self._work_items = work_items
        self._events = events

    async def _event_streams(
        self, *, team_id: UUID | None, project_id: UUID | None
    ) -> list[list[Event]]:
        """One ordered-later event list per work item in the scope (empty lists dropped)."""
        items = await self._work_items.list(team_id=team_id, project_id=project_id)
        events = await self._events.list_for_work_items([item.id for item in items])
        by_item: defaultdict[UUID, list[Event]] = defaultdict(list)
        for event in events:
            by_item[event.work_item_id].append(event)
        return [by_item[item.id] for item in items if by_item[item.id]]

    async def get_flow_metrics(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 30,
        now: datetime | None = None,
    ) -> FlowMetrics:
        """Compute the scope's flow metrics over the trailing window ending at `now`."""
        window_end = now if now is not None else datetime.now(UTC)
        streams = await self._event_streams(team_id=team_id, project_id=project_id)
        samples = [
            sample for stream in streams if (sample := derive_flow_sample(stream)) is not None
        ]
        return compute_flow_metrics(samples, now=window_end, window_days=window_days)

    async def get_flow_history(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 90,
        now: datetime | None = None,
    ) -> FlowHistory:
        """Compute the scope's chart time series over the trailing window."""
        window_end = now if now is not None else datetime.now(UTC)
        streams = await self._event_streams(team_id=team_id, project_id=project_id)
        return compute_flow_history(streams, now=window_end, window_days=window_days)
