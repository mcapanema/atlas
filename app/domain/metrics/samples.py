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


def derive_flow_sample(events: list[Event]) -> FlowSample | None:
    """Fold one work item's events into a FlowSample; None if it has no events.

    created_at is the first event; started_at the first STARTED; completed_at
    the last COMPLETED, voided if a later STARTED reopened the item. Blocked
    time sums blocked periods, clamping a still-open period to completed_at;
    an open period on an uncompleted item is not counted (unmeasurable).
    """
    if not events:
        return None
    ordered = sorted(events, key=lambda e: e.occurred_at)

    started_at = next((e.occurred_at for e in ordered if e.type is EventType.STARTED), None)

    # ponytail: a reopen is only visible as a STARTED after COMPLETED; a
    # Done -> Cancelled move arrives as STATE_CHANGED and still counts as
    # completed. Categorize state *types* in the domain if that ever skews
    # the numbers.
    completed_at: datetime | None = None
    for event in ordered:
        if event.type is EventType.COMPLETED:
            completed_at = event.occurred_at
        elif event.type is EventType.STARTED and completed_at is not None:
            completed_at = None

    blocked_time = timedelta(0)
    for period in derive_timeline(ordered).blocked_periods:
        ended_at = period.ended_at or completed_at
        if ended_at is not None and ended_at > period.started_at:
            blocked_time += ended_at - period.started_at

    return FlowSample(
        created_at=ordered[0].occurred_at,
        started_at=started_at,
        completed_at=completed_at,
        blocked_time=blocked_time,
    )
