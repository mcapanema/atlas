from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.events.entities import Event, EventType
from app.domain.events.timeline import BlockedPeriod, blocked_periods, creation_state
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules, resolve_rules
from app.domain.metrics.flow_efficiency import flow_efficiency
from app.domain.metrics.samples import derive_flow_sample

ITEM = uuid4()


def _day(day: int) -> datetime:
    return datetime(2026, 9, day, tzinfo=UTC)


def _at(type_: EventType, day: int, detail: str | None = None) -> Event:
    return Event(work_item_id=ITEM, type=type_, occurred_at=_day(day), detail=detail)


def _move(type_: EventType, day: int, from_state: str, to_state: str) -> Event:
    return Event(
        work_item_id=ITEM,
        type=type_,
        occurred_at=_day(day),
        from_state=from_state,
        to_state=to_state,
    )


# Started day 2, Blocked days 3-5, Done day 6: a 4-day cycle, 2 days blocked.
BLOCKED_THEN_DONE = [
    _at(EventType.CREATED, 1),
    _move(EventType.STARTED, 2, "Todo", "In Progress"),
    _move(EventType.STATE_CHANGED, 3, "In Progress", "Blocked"),
    _move(EventType.STATE_CHANGED, 5, "Blocked", "In Progress"),
    _move(EventType.COMPLETED, 6, "In Progress", "Done"),
]


def test_states_named_like_blocked_count_by_default() -> None:
    assert DEFAULT_RULES.blocked_state_pattern is True
    assert DEFAULT_RULES.blocked_state_names == ()
    assert DEFAULT_RULES.is_blocked_state("Blocked")
    assert DEFAULT_RULES.is_blocked_state("Blocked by vendor")
    assert not DEFAULT_RULES.is_blocked_state("Unblocked")
    assert not DEFAULT_RULES.is_blocked_state("In Progress")


def test_listed_state_names_count_and_the_pattern_can_be_turned_off() -> None:
    rules = resolve_rules(
        {"blocked_state_pattern": False, "blocked_state_names": [" Aguardando cliente "]}
    )

    assert rules.blocked_state_names == ("Aguardando cliente",)
    assert rules.is_blocked_state("aguardando CLIENTE")
    assert not rules.is_blocked_state("Blocked")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"blocked_state_names": [""]}, "blocked_state_names"),
        ({"blocked_state_names": "Blocked"}, "blocked_state_names"),
        ({"blocked_state_pattern": "yes"}, "blocked_state_pattern"),
    ],
)
def test_invalid_blocked_state_rules_are_rejected(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_rules(overrides)


def test_a_stay_in_a_blocked_state_is_a_blocked_period() -> None:
    assert blocked_periods(BLOCKED_THEN_DONE) == (BlockedPeriod(_day(3), _day(5)),)
    assert blocked_periods(BLOCKED_THEN_DONE, MetricRules(blocked_state_pattern=False)) == ()


def test_moving_between_blocked_states_keeps_one_period() -> None:
    # Review focus 2.
    rules = MetricRules(blocked_state_names=("Aguardando cliente",))
    events = [
        _at(EventType.CREATED, 1),
        _move(EventType.STARTED, 2, "Todo", "In Progress"),
        _move(EventType.STATE_CHANGED, 3, "In Progress", "Blocked"),
        _move(EventType.STATE_CHANGED, 4, "Blocked", "Aguardando cliente"),
        _move(EventType.STATE_CHANGED, 6, "Aguardando cliente", "In Review"),
    ]

    assert blocked_periods(events, rules) == (BlockedPeriod(_day(3), _day(6)),)


def test_a_state_block_overlapping_a_label_block_is_one_period() -> None:
    # Review focus 3.
    events = [
        _at(EventType.CREATED, 1),
        _move(EventType.STARTED, 2, "Todo", "Blocked"),
        _at(EventType.LABEL_ADDED, 3, "Blocked"),
        _move(EventType.STATE_CHANGED, 4, "Blocked", "In Progress"),
        _at(EventType.LABEL_REMOVED, 5, "Blocked"),
    ]

    assert blocked_periods(events) == (BlockedPeriod(_day(2), _day(5)),)


def test_an_item_created_in_a_blocked_state_is_blocked_from_creation() -> None:
    # Review focus 1: Linear history has no creation entry; the mapping stamps
    # STARTED at creation (born in a started-type state) without state names.
    events = [
        _at(EventType.CREATED, 1),
        _at(EventType.STARTED, 1),
        _move(EventType.STATE_CHANGED, 4, "Blocked", "In Progress"),
    ]

    assert blocked_periods(events) == (BlockedPeriod(_day(1), _day(4)),)


def test_an_item_created_in_a_blocked_state_that_never_moved_is_blocked_from_creation() -> None:
    # No transition carries a state name: only the stored current state knows.
    events = [_at(EventType.CREATED, 1), _at(EventType.STARTED, 1)]
    born_in = creation_state(events, current_state="Blocked")

    sample = derive_flow_sample(events, born_in=born_in)

    assert born_in == "Blocked"
    assert blocked_periods(events) == ()  # the events alone can't tell
    assert blocked_periods(events, born_in=born_in) == (BlockedPeriod(_day(1), None),)
    assert sample is not None
    assert sample.blocked_now is True


def test_an_as_of_slice_keeps_the_creation_state_of_the_full_history() -> None:
    full = [
        _at(EventType.CREATED, 1),
        _at(EventType.STARTED, 1),
        _move(EventType.STATE_CHANGED, 6, "Blocked", "In Progress"),
    ]
    as_of_day_5 = full[:2]  # the transition out of Blocked hasn't happened yet

    born_in = creation_state(full, current_state="In Progress")

    assert born_in == "Blocked"  # transitions outrank the current state
    assert blocked_periods(as_of_day_5, born_in=born_in) == (BlockedPeriod(_day(1), None),)


def test_blocked_state_time_lowers_flow_efficiency_and_sets_blocked_now() -> None:
    done = derive_flow_sample(BLOCKED_THEN_DONE)
    still_blocked = derive_flow_sample(BLOCKED_THEN_DONE[:3])

    assert done is not None
    assert still_blocked is not None
    assert done.blocked_time == timedelta(days=2)
    assert flow_efficiency([done]) == 0.5  # 2 of 4 cycle days blocked
    assert still_blocked.blocked_now is True
