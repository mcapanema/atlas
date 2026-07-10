from datetime import UTC, datetime
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.events.timeline import BlockedPeriod, StatePeriod, derive_timeline

WORK_ITEM_ID = uuid4()


def _at(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=UTC)


def _event(
    type: EventType,
    day: int,
    from_state: str | None = None,
    to_state: str | None = None,
) -> Event:
    return Event(
        work_item_id=WORK_ITEM_ID,
        type=type,
        occurred_at=_at(day),
        from_state=from_state,
        to_state=to_state,
    )


def test_empty_events_yield_empty_timeline() -> None:
    timeline = derive_timeline([])

    assert timeline.state_periods == ()
    assert timeline.blocked_periods == ()


def test_transitions_produce_closed_then_open_periods() -> None:
    events = [
        _event(EventType.CREATED, day=1),
        _event(EventType.STARTED, day=3, from_state="Backlog", to_state="In Progress"),
        _event(EventType.COMPLETED, day=6, from_state="In Progress", to_state="Done"),
    ]

    timeline = derive_timeline(events)

    assert timeline.state_periods == (
        StatePeriod(state="Backlog", entered_at=_at(1), exited_at=_at(3)),
        StatePeriod(state="In Progress", entered_at=_at(3), exited_at=_at(6)),
        StatePeriod(state="Done", entered_at=_at(6), exited_at=None),
    )


def test_no_initial_period_without_earlier_event() -> None:
    events = [_event(EventType.STARTED, day=3, from_state="Backlog", to_state="In Progress")]

    timeline = derive_timeline(events)

    assert timeline.state_periods == (
        StatePeriod(state="In Progress", entered_at=_at(3), exited_at=None),
    )


def test_events_are_sorted_before_derivation() -> None:
    events = [
        _event(EventType.COMPLETED, day=6, from_state="In Progress", to_state="Done"),
        _event(EventType.CREATED, day=1),
        _event(EventType.STARTED, day=3, from_state="Backlog", to_state="In Progress"),
    ]

    timeline = derive_timeline(events)

    assert [p.state for p in timeline.state_periods] == ["Backlog", "In Progress", "Done"]


def test_blocked_then_unblocked_closes_period() -> None:
    events = [
        _event(EventType.BLOCKED, day=2),
        _event(EventType.UNBLOCKED, day=4),
    ]

    timeline = derive_timeline(events)

    assert timeline.blocked_periods == (BlockedPeriod(started_at=_at(2), ended_at=_at(4)),)


def test_unmatched_blocked_stays_open() -> None:
    timeline = derive_timeline([_event(EventType.BLOCKED, day=2)])

    assert timeline.blocked_periods == (BlockedPeriod(started_at=_at(2), ended_at=None),)


def test_duplicate_blocked_and_stray_unblocked_are_ignored() -> None:
    events = [
        _event(EventType.UNBLOCKED, day=1),
        _event(EventType.BLOCKED, day=2),
        _event(EventType.BLOCKED, day=3),
        _event(EventType.UNBLOCKED, day=4),
        _event(EventType.UNBLOCKED, day=5),
    ]

    timeline = derive_timeline(events)

    assert timeline.blocked_periods == (BlockedPeriod(started_at=_at(2), ended_at=_at(4)),)
