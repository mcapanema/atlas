"""Derive state and blocked periods from a Work Item's immutable events.

Pure domain logic — Phase 3's flow metrics (blocked time, flow efficiency,
waiting time) build on these periods rather than re-reading raw events.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.events.entities import Event, EventType, event_order
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules


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


def _blocked_source(event: Event, rules: MetricRules) -> tuple[str, bool] | None:
    """(source key, opens?) for an event that opens or closes a blocked source, else None.

    Every state transition is the "state" source: it opens entering a state
    the rules call blocked and closes entering any other (closing a source
    that isn't open is a no-op).
    """
    if event.type in (EventType.BLOCKED, EventType.UNBLOCKED):
        return "explicit", event.type is EventType.BLOCKED
    if event.to_state is not None:
        return "state", rules.is_blocked_state(event.to_state)
    if event.detail is None:
        return None
    if event.type in (EventType.LABEL_ADDED, EventType.LABEL_REMOVED):
        blocked = rules.is_blocked_label(event.detail)
        key = f"label:{event.detail.strip().casefold()}"
        return (key, event.type is EventType.LABEL_ADDED) if blocked else None
    if event.type in (EventType.BLOCKER_ADDED, EventType.BLOCKER_CLEARED):
        key = f"blocker:{event.detail}"
        counted = rules.blocked_by_relations
        return (key, event.type is EventType.BLOCKER_ADDED) if counted else None
    return None


def creation_state(events: list[Event], current_state: str | None = None) -> str | None:
    """The state the item was created in; None when unknown.

    History has no creation entry, so the first transition's from_state is
    the creation state (as in derive_timeline's initial period). With no
    transition the item never left it: it is the stored current state.
    Callers pass the item's full history, so an as-of slice still knows it.
    """
    first = next((e for e in sorted(events, key=event_order) if e.to_state is not None), None)
    return current_state if first is None else first.from_state


def _born_blocked(ordered: list[Event], rules: MetricRules, born_in: str | None) -> bool:
    """The item sat in a blocked state from its first event to its first transition."""
    if not ordered or born_in is None or not rules.is_blocked_state(born_in):
        return False
    first = next((e for e in ordered if e.to_state is not None), None)
    return first is None or ordered[0].occurred_at < first.occurred_at


def blocked_periods(
    events: list[Event], rules: MetricRules = DEFAULT_RULES, *, born_in: str | None = None
) -> tuple[BlockedPeriod, ...]:
    """Blocked intervals under `rules`: blocked while any source is open.

    Sources: explicit BLOCKED/UNBLOCKED events (always), stays in workflow
    states the rules call blocked (one source, so moving between two blocked
    states keeps it open), label events whose label the rules call blocked
    (each label its own source), and — with blocked_by_relations — "blocked
    by" relations (each blocker its own source). Overlapping sources form one
    period, never a double count; a close for a source that isn't open is
    ignored (truncated history).

    `born_in` is the item's creation_state when the caller knows more than
    `events` show (the stored state, or the history after an as-of cut);
    omitted, it is read from `events`.
    """
    ordered = sorted(events, key=event_order)
    periods: list[BlockedPeriod] = []
    open_sources: set[str] = set()
    if _born_blocked(ordered, rules, born_in or creation_state(ordered)):
        open_sources.add("state")
        periods.append(BlockedPeriod(started_at=ordered[0].occurred_at))
    for event in ordered:
        source = _blocked_source(event, rules)
        if source is None:
            continue
        key, opens = source
        was_blocked = bool(open_sources)
        if opens:
            open_sources.add(key)
        else:
            open_sources.discard(key)
        if open_sources and not was_blocked:
            periods.append(BlockedPeriod(started_at=event.occurred_at))
        elif was_blocked and not open_sources:
            periods[-1] = BlockedPeriod(
                started_at=periods[-1].started_at, ended_at=event.occurred_at
            )
    return tuple(periods)


def derive_timeline(
    events: list[Event], rules: MetricRules = DEFAULT_RULES, *, born_in: str | None = None
) -> WorkItemTimeline:
    """Fold a Work Item's events into state periods and blocked periods.

    Events are sorted by `event_order` defensively. State periods come from
    events carrying to_state; if the first such event also names a from_state
    and an earlier event exists (usually CREATED), the gap becomes the initial
    period — the time the item waited in its starting state. Blocked periods
    come from `blocked_periods` under the rules (`born_in` as there).
    """
    ordered = sorted(events, key=event_order)

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

    return WorkItemTimeline(
        state_periods=tuple(state_periods),
        blocked_periods=blocked_periods(ordered, rules, born_in=born_in),
    )
