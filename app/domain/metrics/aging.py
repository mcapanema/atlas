"""Aging WIP: how long current in-progress items have been in flight.

Flags items whose in-progress age exceeds the scope's recent completed
cycle-time percentile (the team's aging_percentile over its aging_history_days,
P85 over 90 days by default) — the "this one is quietly getting stuck" signal
from Kanban practice.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.domain.metric_rules.entities import DEFAULT_RULES
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
    over_percentile: bool
    # Who the item is assigned to as of the last sync; None when unassigned.
    assignee: str | None = None


@dataclass(frozen=True)
class AgingWip:
    """In-progress items at `now`, oldest first, with the cycle-time reference line.

    `cycle_time_percentile` is the `percentile` (the team's aging_percentile)
    of cycle times completed in the trailing `history_days` (its
    aging_history_days); None when nothing completed in them.
    """

    now: datetime
    cycle_time_percentile: timedelta | None
    items: tuple[AgingItem, ...]
    percentile: int = DEFAULT_RULES.aging_percentile
    history_days: int = DEFAULT_RULES.aging_history_days


def completed_cycles(
    samples: Sequence[FlowSample], *, end: datetime, history_days: int
) -> list[timedelta]:
    """Cycle times of the samples completed in (end - history_days, end]."""
    since = end - timedelta(days=history_days)
    return cycle_times(
        [s for s in samples if s.completed_at is not None and since < s.completed_at <= end]
    )


def aging_reference(
    samples: Sequence[FlowSample], *, now: datetime, pct: int, history_days: int
) -> timedelta | None:
    """The `pct` percentile of cycle times completed in (now - history_days, now]."""
    recent = completed_cycles(samples, end=now, history_days=history_days)
    if not recent:
        return None
    return timedelta(seconds=percentile([c.total_seconds() for c in recent], pct))


def compute_aging_wip(
    items_with_samples: list[tuple[WorkItem, FlowSample]],
    *,
    now: datetime,
    aging_percentile: int = DEFAULT_RULES.aging_percentile,
    history_days: int = DEFAULT_RULES.aging_history_days,
) -> AgingWip:
    """Age of every item in progress at `now` (started, not completed).

    The reference line is `aging_reference`; over_percentile is False
    everywhere when nothing completed in the aging history.
    """
    limit = aging_reference(
        [sample for _, sample in items_with_samples],
        now=now,
        pct=aging_percentile,
        history_days=history_days,
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
                over_percentile=limit is not None and age > limit,
                assignee=item.assignee,
            )
        )
    aging.sort(key=lambda a: a.age, reverse=True)
    return AgingWip(
        now=now,
        cycle_time_percentile=limit,
        items=tuple(aging),
        percentile=aging_percentile,
        history_days=history_days,
    )
