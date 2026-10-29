"""Code-host events (REVIEW, MERGED) never anchor an item's flow.

A pull request opened before its ticket was created (the key added to the
PR later) puts a REVIEW event first in the stream; the flow measures must
read exactly as they do without it.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

from app.domain.events.entities import CODE_EVENT_TYPES, Event, EventType
from app.domain.events.timeline import BlockedPeriod, blocked_periods, state_periods
from app.domain.metrics.cfd import DailyFlowCount, daily_flow_counts
from app.domain.metrics.samples import derive_flow_sample

ITEM = uuid4()


def _day(day: int) -> datetime:
    return datetime(2026, 9, day, 12, tzinfo=UTC)


def _at(type_: EventType, day: int) -> Event:
    return Event(work_item_id=ITEM, type=type_, occurred_at=_day(day), detail="api#7")


def _move(type_: EventType, day: int, from_state: str, to_state: str) -> Event:
    return Event(
        work_item_id=ITEM,
        type=type_,
        occurred_at=_day(day),
        from_state=from_state,
        to_state=to_state,
    )


EARLY_REVIEW = _at(EventType.REVIEW, 1)


def test_code_event_types_are_review_and_merged() -> None:
    assert frozenset({EventType.REVIEW, EventType.MERGED}) == CODE_EVENT_TYPES


def test_an_earlier_review_does_not_move_created_at() -> None:
    sample = derive_flow_sample([EARLY_REVIEW, _at(EventType.MERGED, 2), _at(EventType.CREATED, 3)])

    assert sample is not None
    assert sample.created_at == _day(3)


def test_an_earlier_review_keeps_a_created_done_item_born_done() -> None:
    sample = derive_flow_sample(
        [EARLY_REVIEW, _at(EventType.CREATED, 3), _at(EventType.COMPLETED, 3)]
    )

    assert sample is not None
    assert sample.born_done


def test_an_earlier_review_does_not_lengthen_the_first_state_period() -> None:
    events = [
        EARLY_REVIEW,
        _at(EventType.CREATED, 3),
        _move(EventType.STARTED, 5, "Backlog", "In Progress"),
    ]

    assert state_periods(events)[0].entered_at == _day(3)


def test_an_earlier_review_does_not_extend_a_born_blocked_period() -> None:
    events = [
        EARLY_REVIEW,
        _at(EventType.CREATED, 3),
        _move(EventType.STATE_CHANGED, 5, "Blocked", "In Progress"),
    ]

    assert blocked_periods(events) == (BlockedPeriod(_day(3), _day(5)),)


def test_an_earlier_review_does_not_put_the_item_on_the_cfd() -> None:
    counts = daily_flow_counts(
        [[EARLY_REVIEW, _at(EventType.CREATED, 3)]],
        start=_day(1),
        end=_day(3),
    )

    assert counts[0] == DailyFlowCount(day=date(2026, 9, 1), todo=0, in_progress=0, done=0)
    assert counts[2] == DailyFlowCount(day=date(2026, 9, 3), todo=1, in_progress=0, done=0)


def test_a_stream_of_code_events_only_anchors_on_its_first_event() -> None:
    sample = derive_flow_sample([_at(EventType.MERGED, 2), EARLY_REVIEW])

    assert sample is not None
    assert sample.created_at == _day(1)
