"""Aging WIP: how long current in-progress items have been in flight.

Flags items whose in-progress age exceeds the scope's completed cycle-time
percentile (the team's aging_percentile, P85 by default) — the "this one is
quietly getting stuck" signal from Kanban practice.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.domain.metrics.cycle_time import cycle_times
from app.domain.metrics.samples import FlowSample, in_progress
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
    """In-progress items at `now`, oldest first, with the cycle-time reference line.

    `cycle_time_p85` (and AgingItem.over_p85) keep their names for API
    stability; the percentile is `percentile`, the team's aging_percentile.
    """

    now: datetime
    cycle_time_p85: timedelta | None
    items: tuple[AgingItem, ...]
    percentile: int = 85


def compute_aging_wip(
    items_with_samples: list[tuple[WorkItem, FlowSample]],
    *,
    now: datetime,
    aging_percentile: int = 85,
) -> AgingWip:
    """Age of every item in progress at `now` (started, not completed).

    The reference line is the scope's completed cycle-time percentile at
    `aging_percentile`; over_p85 is False everywhere when there is no
    completed history to compare against.
    """
    completed = cycle_times([sample for _, sample in items_with_samples])
    limit = (
        timedelta(seconds=percentile([c.total_seconds() for c in completed], aging_percentile))
        if completed
        else None
    )
    aging: list[AgingItem] = []
    for item, sample in items_with_samples:
        if not in_progress(sample, now) or sample.started_at is None:
            continue
        age = now - sample.started_at
        aging.append(
            AgingItem(
                work_item_id=item.id,
                title=item.title,
                state=item.state,
                age=age,
                over_p85=limit is not None and age > limit,
            )
        )
    aging.sort(key=lambda a: a.age, reverse=True)
    return AgingWip(now=now, cycle_time_p85=limit, items=tuple(aging), percentile=aging_percentile)
