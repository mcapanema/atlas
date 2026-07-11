"""Shared scope loading for the analytics use cases.

Metrics, forecasting, and the advisor all start from the same picture:
every work item in a scope plus each item's ordered events. This module is
the one place that picture gets assembled — a semantic drift between two
copies of this loop is exactly where remaining-count bugs hide.
"""

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from app.domain.events.entities import Event
from app.domain.events.repository import EventRepository
from app.domain.metrics.samples import FlowSample, derive_flow_sample
from app.domain.work_items.repository import WorkItemRepository


@dataclass(frozen=True)
class ScopeSamples:
    """One scope load: per-item event streams, derived samples, item count.

    `streams` holds one occurred_at-ordered event list per work item that
    has events. `item_count` counts every item in the scope, including
    eventless backlog — it is the forecast's remaining-work denominator.
    """

    streams: list[list[Event]]
    samples: list[FlowSample]
    item_count: int


class ScopeSampleLoader:
    """Loads a scope's items + events once and derives the flow samples."""

    def __init__(self, work_items: WorkItemRepository, events: EventRepository) -> None:
        self._work_items = work_items
        self._events = events

    async def load(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> ScopeSamples:
        items = await self._work_items.list(team_id=team_id, project_id=project_id)
        events = await self._events.list_for_work_items([item.id for item in items])
        by_item: defaultdict[UUID, list[Event]] = defaultdict(list)
        for event in events:
            by_item[event.work_item_id].append(event)
        streams = [by_item[item.id] for item in items if by_item[item.id]]
        samples = [
            sample
            for stream in streams
            if (sample := derive_flow_sample(stream)) is not None
        ]
        return ScopeSamples(streams=streams, samples=samples, item_count=len(items))
