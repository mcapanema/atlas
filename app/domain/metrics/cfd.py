"""Cumulative flow: per-day counts of work items in each flow phase.

Replays every item's events in one chronological pass, so past days stay
correct even when an item is later reopened (FlowSample voids completed_at
on reopen, which would rewrite history — see wip.py).
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


def _advance(phase: str | None, event: Event) -> str:
    """The item's phase after `event`, given its phase before it."""
    if event.type is EventType.STARTED:
        return "in_progress"
    if event.type is EventType.COMPLETED:
        return "done"
    return phase if phase is not None else "todo"


def daily_flow_counts(
    event_streams: list[list[Event]], *, start: datetime, end: datetime
) -> list[DailyFlowCount]:
    """One DailyFlowCount per UTC calendar day from start to end, inclusive.

    Each day is measured at end-of-day (23:59:59.999999 UTC), clamped to
    `end` for the final day. One chronological pass over all events carries
    each item's phase forward — O(events·log(events) + days), replacing the
    per-day replay that was O(days × events).

    ponytail: three phases derived from event types (not per-Workflow-State
    bands) — add stage-level bands if teams want per-state CFDs.
    """
    ordered = sorted(
        (
            (event.occurred_at, item_index, event)
            for item_index, stream in enumerate(event_streams)
            for event in stream
        ),
        key=lambda entry: (entry[0], entry[1]),
    )
    phases: dict[int, str] = {}
    tally = {"todo": 0, "in_progress": 0, "done": 0}
    counts: list[DailyFlowCount] = []
    pointer = 0
    day = start.astimezone(UTC).date()
    last = end.astimezone(UTC).date()
    while day <= last:
        instant = min(end, datetime.combine(day, time.max, tzinfo=UTC))
        while pointer < len(ordered) and ordered[pointer][0] <= instant:
            _, item_index, event = ordered[pointer]
            before = phases.get(item_index)
            after = _advance(before, event)
            if before is not None:
                tally[before] -= 1
            tally[after] += 1
            phases[item_index] = after
            pointer += 1
        counts.append(
            DailyFlowCount(
                day=day,
                todo=tally["todo"],
                in_progress=tally["in_progress"],
                done=tally["done"],
            )
        )
        day += timedelta(days=1)
    return counts
