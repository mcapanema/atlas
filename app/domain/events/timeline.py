"""Derive state and blocked periods from a Work Item's immutable events.

Pure domain logic — Phase 3's flow metrics (blocked time, flow efficiency,
waiting time) build on these periods rather than re-reading raw events.
"""

from dataclasses import dataclass
from datetime import datetime
from itertools import groupby

from app.domain.events.entities import Event, EventType, event_order
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules


def _chain(group: list[Event], before: str | None) -> list[Event]:
    """One instant's events with its moves following their from/to state chain.

    The chain starts at the state the item was in (`before`), or — with no
    earlier move — at the from-state no move in the instant enters. A chain
    that can't be followed keeps storage order.
    """
    moves = [e for e in group if e.to_state is not None]
    if len(moves) < 2:
        return group
    state = before
    if state is None:
        entered = {m.to_state for m in moves}
        state = next((m.from_state for m in moves if m.from_state not in entered), None)
    chain: list[Event] = []
    pending = list(moves)
    while pending:
        step = next((m for m in pending if m.from_state == state), None)
        if step is None:
            return group
        chain.append(step)
        pending.remove(step)
        state = step.to_state
    steps = iter(chain)
    return [next(steps) if e.to_state is not None else e for e in group]


def chain_order(events: list[Event]) -> list[Event]:
    """Events in `event_order`, with same-instant moves replayed along their state chain.

    Linear automations can write several moves with one timestamp, and
    storage order must not decide which state the item ended in. Only the
    state and blocked periods use this; the lifecycle keeps event_order.
    """
    ordered: list[Event] = []
    state: str | None = None
    for _, run in groupby(sorted(events, key=event_order), key=lambda e: e.occurred_at):
        group = _chain(list(run), state)
        ordered.extend(group)
        state = next((e.to_state for e in reversed(group) if e.to_state is not None), state)
    return ordered


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
    first = next((e for e in chain_order(events) if e.to_state is not None), None)
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
    ordered = chain_order(events)
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
            _close(periods, event.occurred_at)
    return tuple(periods)


def _close(periods: list[BlockedPeriod], at: datetime) -> None:
    """End the open period at `at`; one opened at that same instant held no time, so drop it."""
    started_at = periods[-1].started_at
    if started_at == at:
        periods.pop()
    else:
        periods[-1] = BlockedPeriod(started_at=started_at, ended_at=at)


def derive_timeline(
    events: list[Event], rules: MetricRules = DEFAULT_RULES, *, born_in: str | None = None
) -> WorkItemTimeline:
    """Fold a Work Item's events into state periods and blocked periods.

    Events are put in `chain_order` defensively. State periods come from
    events carrying to_state; if the first such event also names a from_state
    and an earlier event exists (usually CREATED), the gap becomes the initial
    period — the time the item waited in its starting state. Blocked periods
    come from `blocked_periods` under the rules (`born_in` as there).
    """
    ordered = chain_order(events)

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
