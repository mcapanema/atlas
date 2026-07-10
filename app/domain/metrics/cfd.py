"""Cumulative flow: per-day counts of work items in each flow phase.

Replays each item's event stream to get its phase at an instant, so past
days stay correct even when an item is later reopened (FlowSample voids
completed_at on reopen, which would rewrite history — see wip.py).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from app.domain.events.entities import Event, EventType


@dataclass(frozen=True)
class DailyFlowCount:
    """Work-item counts per flow phase at the end of one UTC calendar day."""

    day: date
    todo: int
    in_progress: int
    done: int


def _phase_at(ordered: list[Event], at: datetime) -> str | None:
    """The item's phase at `at`, or None if it has no events yet."""
    phase: str | None = None
    for event in ordered:
        if event.occurred_at > at:
            break
        if phase is None:
            phase = "todo"
        if event.type is EventType.STARTED:
            phase = "in_progress"
        elif event.type is EventType.COMPLETED:
            phase = "done"
    return phase


def daily_flow_counts(
    event_streams: list[list[Event]], *, start: datetime, end: datetime
) -> list[DailyFlowCount]:
    """One DailyFlowCount per UTC calendar day from start to end, inclusive.

    Each day is measured at end-of-day (23:59:59.999999 UTC), clamped to
    `end` for the final day.

    ponytail: three phases derived from event types (not per-Workflow-State
    bands) and an O(days x events) replay — add stage-level bands and a
    precomputed transition index if teams want per-state CFDs.
    """
    ordered_streams = [
        sorted(stream, key=lambda e: e.occurred_at) for stream in event_streams if stream
    ]
    counts: list[DailyFlowCount] = []
    day = start.astimezone(UTC).date()
    last = end.astimezone(UTC).date()
    while day <= last:
        instant = min(end, datetime.combine(day, time.max, tzinfo=UTC))
        todo = in_progress = done = 0
        for stream in ordered_streams:
            phase = _phase_at(stream, instant)
            if phase == "todo":
                todo += 1
            elif phase == "in_progress":
                in_progress += 1
            elif phase == "done":
                done += 1
        counts.append(DailyFlowCount(day=day, todo=todo, in_progress=in_progress, done=done))
        day += timedelta(days=1)
    return counts
