"""Aging WIP: how long current in-progress items have been in flight.

Flags items whose in-progress age exceeds the scope's completed cycle-time
P85 — the "this one is quietly getting stuck" signal from Kanban practice.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.domain.metrics.cycle_time import cycle_times
from app.domain.metrics.samples import FlowSample
from app.domain.metrics.stats import percentile
from app.domain.work_items.entities import WorkItem


@dataclass(frozen=True)
class AgingItem:
    """One in-progress work item and how long it has been in progress."""

    work_item_id: UUID
    title: str
    state: str
    age: timedelta
    over_p85: bool


@dataclass(frozen=True)
class AgingWip:
    """In-progress items at `now`, oldest first, with the P85 reference line."""

    now: datetime
    cycle_time_p85: timedelta | None
    items: tuple[AgingItem, ...]


def compute_aging_wip(
    items_with_samples: list[tuple[WorkItem, FlowSample]], *, now: datetime
) -> AgingWip:
    """Age of every item in progress at `now` (started, not completed).

    cycle_time_p85 comes from the scope's completed samples; over_p85 is
    False everywhere when there is no completed history to compare against.
    """
    completed = cycle_times([sample for _, sample in items_with_samples])
    p85 = (
        timedelta(seconds=percentile([c.total_seconds() for c in completed], 85))
        if completed
        else None
    )
    aging: list[AgingItem] = []
    for item, sample in items_with_samples:
        if sample.started_at is None or sample.started_at > now:
            continue
        if sample.completed_at is not None and sample.completed_at <= now:
            continue
        age = now - sample.started_at
        aging.append(
            AgingItem(
                work_item_id=item.id,
                title=item.title,
                state=item.state,
                age=age,
                over_p85=p85 is not None and age > p85,
            )
        )
    aging.sort(key=lambda a: a.age, reverse=True)
    return AgingWip(now=now, cycle_time_p85=p85, items=tuple(aging))
