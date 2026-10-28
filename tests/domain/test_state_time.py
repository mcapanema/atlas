from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.domain.events.entities import Event, EventType
from app.domain.metrics.samples import FlowSample, derive_flow_sample
from app.domain.metrics.state_time import StateTime, StateTimes, compute_state_times
from tests.fakes import CALENDAR_DAYS

RULES = replace(CALENDAR_DAYS, wait_state_names=("In Review",), health_min_sample=2)
NOW = datetime(2026, 9, 30, tzinfo=UTC)


def _day(day: int) -> datetime:
    return datetime(2026, 9, day, tzinfo=UTC)


def _move(item: UUID, type_: EventType, day: int, from_state: str, to_state: str) -> Event:
    return Event(
        work_item_id=item,
        type=type_,
        occurred_at=_day(day),
        from_state=from_state,
        to_state=to_state,
    )


def _item_a() -> list[Event]:
    item = uuid4()
    return [
        Event(work_item_id=item, type=EventType.CREATED, occurred_at=_day(1)),
        _move(item, EventType.STARTED, 2, "Todo", "In Progress"),
        _move(item, EventType.STATE_CHANGED, 4, "In Progress", "In Review"),
        _move(item, EventType.COMPLETED, 9, "In Review", "Done"),
    ]


def _item_b() -> list[Event]:
    item = uuid4()
    return [
        _move(item, EventType.STARTED, 10, "Todo", "In Progress"),
        _move(item, EventType.STATE_CHANGED, 11, "In Progress", "In Review"),
        _move(item, EventType.COMPLETED, 14, "In Review", "Done"),
    ]


def _item_c(waits_in: str = "In Review") -> list[Event]:
    item = uuid4()
    return [
        _move(item, EventType.STARTED, 20, "Todo", "In Progress"),
        _move(item, EventType.STATE_CHANGED, 25, "In Progress", waits_in),
    ]


def _sample(events: list[Event]) -> FlowSample:
    sample = derive_flow_sample(events, RULES)
    assert sample is not None
    return sample


def _compute(*streams: list[Event], window_days: int = 30) -> StateTimes:
    return compute_state_times(
        list(streams),
        [_sample(stream) for stream in streams],
        now=NOW,
        window_days=window_days,
        rules=RULES,
    )


def test_sums_in_cycle_time_per_state_and_names_the_largest_as_bottleneck() -> None:
    result = _compute(_item_a(), _item_b())

    assert [s.state for s in result.states] == ["In Review", "In Progress"]
    review, progress = result.states
    assert review.total == timedelta(days=8)
    assert review.items == 2
    assert review.median == timedelta(days=4)
    assert review.wait_state is True
    assert review.share == pytest.approx(8 / 11)
    assert progress.total == timedelta(days=3)
    assert progress.wait_state is False
    assert result.measured == 2
    assert result.bottleneck == "In Review"


def test_queue_counts_items_in_progress_by_their_state_at_now() -> None:
    result = _compute(_item_a(), _item_b(), _item_c())

    by_state = {s.state: s for s in result.states}
    assert by_state["In Review"].queue == 1
    assert by_state["In Progress"].queue == 0
    assert by_state["In Review"].total == timedelta(days=8)
    assert by_state["In Progress"].total == timedelta(days=3)


def test_a_state_with_only_a_queue_is_listed_with_zero_time() -> None:
    result = _compute(_item_c("QA"))

    assert result.states == (StateTime("QA", timedelta(0), 0.0, timedelta(0), 0, 1, False),)
    assert result.bottleneck is None


def test_no_bottleneck_below_the_minimum_sample() -> None:
    result = _compute(_item_a())

    assert result.measured == 1
    assert result.min_sample == 2
    assert result.states
    assert result.bottleneck is None


def test_items_without_state_moves_are_not_measured() -> None:
    item = uuid4()
    stream = [
        Event(work_item_id=item, type=type_, occurred_at=_day(day))
        for type_, day in (
            (EventType.CREATED, 1),
            (EventType.STARTED, 2),
            (EventType.COMPLETED, 5),
        )
    ]

    result = _compute(stream)

    assert result.measured == 0
    assert result.states == ()
    assert result.bottleneck is None


def test_completions_outside_the_window_are_ignored() -> None:
    result = _compute(_item_a(), window_days=5)

    assert result.measured == 0
    assert result.states == ()
