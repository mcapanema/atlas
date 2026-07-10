from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from app.domain.events.entities import Event
from app.domain.events.repository import EventRepository
from app.domain.metrics.samples import derive_flow_sample
from app.domain.metrics.summary import TeamFlowMetrics, compute_team_metrics
from app.domain.work_items.repository import WorkItemRepository


class MetricsService:
    """Application use cases for flow metrics."""

    def __init__(self, work_items: WorkItemRepository, events: EventRepository) -> None:
        self._work_items = work_items
        self._events = events

    async def get_team_flow_metrics(
        self, team_id: UUID, *, window_days: int = 30, now: datetime | None = None
    ) -> TeamFlowMetrics:
        """Compute a team's flow metrics over the trailing window ending at `now`."""
        window_end = now if now is not None else datetime.now(UTC)
        items = await self._work_items.list(team_id=team_id)
        events = await self._events.list_for_work_items([item.id for item in items])
        events_by_item: defaultdict[UUID, list[Event]] = defaultdict(list)
        for event in events:
            events_by_item[event.work_item_id].append(event)
        samples = [
            sample
            for item in items
            if (sample := derive_flow_sample(events_by_item[item.id])) is not None
        ]
        return compute_team_metrics(samples, now=window_end, window_days=window_days)
