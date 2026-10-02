"""Per-work-item flow measures derived from its immutable events.

The bridge between raw events and the flow metrics: every metric consumes
FlowSamples instead of re-reading event streams.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.events.entities import Event, EventType
from app.domain.events.timeline import derive_timeline


@dataclass(frozen=True)
class FlowSample:
    """One work item's flow measures. A None field means 'has not happened'."""

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    blocked_time: timedelta
    stopped_at: datetime | None = None
    canceled: bool = False


def derive_flow_sample(events: list[Event]) -> FlowSample | None:
    """Fold one work item's events into a FlowSample; None if it has no events.

    created_at is the first event; started_at the first STARTED; completed_at
    the last COMPLETED, voided if a later STARTED reopened the item.
    stopped_at is when an uncompleted item last left progress (STOPPED or CANCELED
    since its latest STARTED); canceled marks an item closed without delivery. Blocked
    time sums blocked periods clipped to the cycle — from started_at (or the
    first event, if never started) to completed_at; a still-open period on an
    uncompleted item is not counted (unmeasurable).
    """
    if not events:
        return None
    ordered = sorted(events, key=lambda e: e.occurred_at)

    started_at = next((e.occurred_at for e in ordered if e.type is EventType.STARTED), None)

    # ponytail: Done -> Todo isn't a reopen here (only a STARTED after
    # COMPLETED is), so it stays completed; Done -> Canceled stays delivered
    # by decision. Categorize state *types* in the domain if either skews
    # the numbers.
    completed_at: datetime | None = None
    stopped_at: datetime | None = None
    canceled = False
    for event in ordered:
        if event.type is EventType.COMPLETED:
            completed_at, stopped_at, canceled = event.occurred_at, None, False
        elif event.type is EventType.STARTED:
            completed_at, stopped_at, canceled = None, None, False
        elif event.type in (EventType.STOPPED, EventType.CANCELED) and completed_at is None:
            if stopped_at is None:
                stopped_at = event.occurred_at
            canceled = canceled or event.type is EventType.CANCELED

    # Blocked time is measured inside the item's cycle: a label left on after
    # Done isn't blocked work, and pre-start blocking is already queue time.
    cycle_start = started_at if started_at is not None else ordered[0].occurred_at
    blocked_time = timedelta(0)
    for period in derive_timeline(ordered).blocked_periods:
        ended_at = period.ended_at
        if completed_at is not None:
            ended_at = completed_at if ended_at is None else min(ended_at, completed_at)
        begun = max(period.started_at, cycle_start)
        if ended_at is not None and ended_at > begun:
            blocked_time += ended_at - begun

    return FlowSample(
        created_at=ordered[0].occurred_at,
        started_at=started_at,
        completed_at=completed_at,
        blocked_time=blocked_time,
        stopped_at=stopped_at,
        canceled=canceled,
    )


def in_progress(sample: FlowSample, at: datetime) -> bool:
    """Started by `at`, and neither completed nor stopped (moved back/canceled) by it."""
    if sample.started_at is None or sample.started_at > at:
        return False
    return all(ended is None or ended > at for ended in (sample.completed_at, sample.stopped_at))
