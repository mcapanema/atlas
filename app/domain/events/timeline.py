"""Derive state and blocked periods from a Work Item's immutable events.

Pure domain logic — Phase 3's flow metrics (blocked time, flow efficiency,
waiting time) build on these periods rather than re-reading raw events.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.events.entities import Event, EventType


@dataclass(frozen=True)
class StatePeriod:
    """A contiguous stay in one workflow state. exited_at=None means still there."""

    state: str
    entered_at: datetime
    exited_at: datetime | None = None


@dataclass(frozen=True)
class BlockedPeriod:
    """A blocked interval. ended_at=None means still blocked."""

    started_at: datetime
    ended_at: datetime | None = None


@dataclass(frozen=True)
class WorkItemTimeline:
    """State and blocked history derived from a Work Item's events."""

    state_periods: tuple[StatePeriod, ...]
    blocked_periods: tuple[BlockedPeriod, ...]


def derive_timeline(events: list[Event]) -> WorkItemTimeline:
    """Fold a Work Item's events into state periods and blocked periods.

    Events are sorted by occurred_at defensively. State periods come from
    events carrying to_state; if the first such event also names a from_state
    and an earlier event exists (usually CREATED), the gap becomes the initial
    period — the time the item waited in its starting state. Blocked periods
    pair BLOCKED with the next UNBLOCKED; an unmatched BLOCKED stays open.
    """
    ordered = sorted(events, key=lambda e: e.occurred_at)

    state_periods: list[StatePeriod] = []
    for event in ordered:
        if event.to_state is None:
            continue
        if state_periods:
            previous = state_periods[-1]
            state_periods[-1] = StatePeriod(
                state=previous.state,
                entered_at=previous.entered_at,
                exited_at=event.occurred_at,
            )
        elif event.from_state is not None and ordered[0].occurred_at < event.occurred_at:
            state_periods.append(
                StatePeriod(
                    state=event.from_state,
                    entered_at=ordered[0].occurred_at,
                    exited_at=event.occurred_at,
                )
            )
        state_periods.append(StatePeriod(state=event.to_state, entered_at=event.occurred_at))

    blocked_periods: list[BlockedPeriod] = []
    for event in ordered:
        has_open_block = bool(blocked_periods) and blocked_periods[-1].ended_at is None
        if event.type is EventType.BLOCKED and not has_open_block:
            blocked_periods.append(BlockedPeriod(started_at=event.occurred_at))
        elif event.type is EventType.UNBLOCKED and has_open_block:
            blocked_periods[-1] = BlockedPeriod(
                started_at=blocked_periods[-1].started_at,
                ended_at=event.occurred_at,
            )

    return WorkItemTimeline(
        state_periods=tuple(state_periods),
        blocked_periods=tuple(blocked_periods),
    )
