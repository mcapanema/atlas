"""Cumulative flow: per-day counts of work items in each flow phase.

Replays every item's events in one chronological pass (same-instant events
replay in lifecycle order, see `event_order`), so past days stay
correct even when an item is later reopened (FlowSample voids completed_at
on reopen, which would rewrite history — see wip.py).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from app.domain.events.entities import Event, EventType, event_order
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules


@dataclass(frozen=True)
class DailyFlowCount:
    """Work-item counts per flow phase at the end of one calendar day in the scope's timezone."""

    day: date
    todo: int
    in_progress: int
    done: int


def _advance(phase: str | None, event: Event, rules: MetricRules = DEFAULT_RULES) -> str:
    """The item's phase after `event`, given its phase before it.

    "canceled" is a hidden phase: closed undelivered items drop out of the
    chart. Done stays done through a cancel (delivered work stays
    delivered) unless the team's done_then_canceled rule un-delivers it. A
    STOPPED never lifts an item out of "canceled" (the derived stop can sort
    after the cancel when their timestamps skew or tie), and it's ignored
    when the team's move_back_ends_wip rule is off.
    """
    if event.type is EventType.STARTED:
        return "in_progress"
    if event.type is EventType.COMPLETED:
        return "done"
    if phase == "done":
        undelivered = event.type is EventType.CANCELED and rules.done_then_canceled == "canceled"
        return "canceled" if undelivered else phase
    if event.type is EventType.STOPPED and rules.move_back_ends_wip:
        return "todo" if phase != "canceled" else phase
    if event.type is EventType.CANCELED:
        return "canceled"
    return phase if phase is not None else "todo"


def daily_flow_counts(
    event_streams: list[list[Event]],
    *,
    start: datetime,
    end: datetime,
    tz: tzinfo = UTC,
    stream_rules: Sequence[MetricRules] | None = None,
) -> list[DailyFlowCount]:
    """One DailyFlowCount per calendar day in `tz` from start to end, inclusive.

    Each day is measured at its local end-of-day (23:59:59.999999 in `tz`),
    clamped to `end` for the final day. `stream_rules[i]` (the item's team's
    rules; built-in when omitted) folds `event_streams[i]`. One chronological
    pass over all events carries each item's phase forward — O(events·log(events)
    + days), replacing the per-day replay that was O(days * events).

    ponytail: three phases derived from event types (not per-Workflow-State
    bands) — add stage-level bands if teams want per-state CFDs.
    """
    ordered = sorted(
        (
            (event.occurred_at, item_index, event)
            for item_index, stream in enumerate(event_streams)
            for event in stream
        ),
        key=lambda entry: (event_order(entry[2]), entry[1]),
    )
    phases: dict[int, str] = {}
    tally = {"todo": 0, "in_progress": 0, "done": 0, "canceled": 0}
    counts: list[DailyFlowCount] = []
    pointer = 0
    day = start.astimezone(tz).date()
    last = end.astimezone(tz).date()
    while day <= last:
        # fold=1: the later of a repeated hour, so a midnight DST end keeps the full day.
        instant = min(end, datetime.combine(day, time.max.replace(fold=1), tzinfo=tz))
        while pointer < len(ordered) and ordered[pointer][0] <= instant:
            _, item_index, event = ordered[pointer]
            # Empty or omitted (a hand-built ScopeSamples): built-in rules.
            rules = stream_rules[item_index] if stream_rules else DEFAULT_RULES
            before = phases.get(item_index)
            after = _advance(before, event, rules)
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
