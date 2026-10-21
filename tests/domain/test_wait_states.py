from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules, resolve_rules
from app.domain.metrics.flow_efficiency import flow_efficiency
from app.domain.metrics.samples import FlowSample, derive_flow_sample
from tests.fakes import CALENDAR_DAYS

ITEM = uuid4()
WAIT = replace(CALENDAR_DAYS, wait_state_names=("In Review",))


def test_no_wait_states_by_default() -> None:
    assert DEFAULT_RULES.wait_state_names == ()
    assert not DEFAULT_RULES.is_wait_state("In Review")


def test_listed_wait_states_match_by_whole_name_in_any_case() -> None:
    rules = resolve_rules({"wait_state_names": [" in review ", "Waiting for Deploy"]})

    assert rules.wait_state_names == ("in review", "Waiting for Deploy")
    assert rules.is_wait_state("In Review")
    assert rules.is_wait_state("waiting for deploy")
    assert not rules.is_wait_state("In Progress")
    assert not rules.is_wait_state("In Review 2")


@pytest.mark.parametrize("value", ["In Review", [""]])
def test_invalid_wait_state_names_are_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="wait_state_names"):
        resolve_rules({"wait_state_names": value})


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


def _sample(events: list[Event], rules: MetricRules = WAIT) -> FlowSample:
    sample = derive_flow_sample(events, rules)
    assert sample is not None
    return sample


# Started day 2, In Review days 4-7, Done day 7: a 5-day cycle, 3 days waiting.
REVIEW_THEN_DONE = [
    _at(EventType.CREATED, 1),
    _move(EventType.STARTED, 2, "Todo", "In Progress"),
    _move(EventType.STATE_CHANGED, 4, "In Progress", "In Review"),
    _move(EventType.COMPLETED, 7, "In Review", "Done"),
]


def test_review_stay_inside_cycle_is_state_wait() -> None:
    sample = _sample(REVIEW_THEN_DONE)

    assert sample.state_wait_time == timedelta(days=3)
    assert sample.blocked_time == timedelta(0)
    assert sample.wait_time == timedelta(days=3)


def test_unlisted_state_is_not_wait() -> None:
    sample = _sample(REVIEW_THEN_DONE, CALENDAR_DAYS)

    assert sample.state_wait_time == timedelta(0)
    assert sample.wait_time == timedelta(0)


def test_state_both_blocked_and_waiting_counts_once() -> None:
    rules = replace(
        WAIT,
        blocked_state_names=("Aguardando cliente",),
        wait_state_names=("Aguardando cliente",),
    )
    sample = _sample(
        [
            _at(EventType.CREATED, 1),
            _move(EventType.STARTED, 2, "Todo", "In Progress"),
            _move(EventType.STATE_CHANGED, 3, "In Progress", "Aguardando cliente"),
            _move(EventType.COMPLETED, 6, "Aguardando cliente", "Done"),
        ],
        rules,
    )

    assert sample.blocked_time == timedelta(days=3)
    assert sample.state_wait_time == timedelta(0)
    assert sample.wait_time == timedelta(days=3)


def test_blocked_label_during_review_counts_once() -> None:
    sample = _sample(
        [
            _at(EventType.CREATED, 1),
            _move(EventType.STARTED, 2, "Todo", "In Progress"),
            _move(EventType.STATE_CHANGED, 3, "In Progress", "In Review"),
            _at(EventType.LABEL_ADDED, 4, "Blocked"),
            _at(EventType.LABEL_REMOVED, 5, "Blocked"),
            _move(EventType.COMPLETED, 6, "In Review", "Done"),
        ]
    )

    assert sample.blocked_time == timedelta(days=1)
    assert sample.state_wait_time == timedelta(days=2)


def test_review_after_completion_is_not_wait() -> None:
    sample = _sample(
        [
            _at(EventType.CREATED, 1),
            _move(EventType.STARTED, 2, "Todo", "In Progress"),
            _move(EventType.COMPLETED, 5, "In Progress", "Done"),
            _move(EventType.STATE_CHANGED, 6, "Done", "In Review"),
        ]
    )

    assert sample.completed_at == _day(5)
    assert sample.state_wait_time == timedelta(0)


def test_review_before_a_restarted_clock_is_not_wait() -> None:
    rules = replace(WAIT, restart_clock_after_move_back=True)
    sample = _sample(
        [
            _at(EventType.CREATED, 1),
            _move(EventType.STARTED, 2, "Todo", "In Review"),
            _move(EventType.STOPPED, 3, "In Review", "Todo"),
            _move(EventType.STARTED, 4, "Todo", "In Progress"),
            _move(EventType.COMPLETED, 6, "In Progress", "Done"),
        ],
        rules,
    )

    assert sample.started_at == _day(4)
    assert sample.state_wait_time == timedelta(0)


def test_open_review_on_an_unfinished_item_adds_nothing() -> None:
    sample = _sample(REVIEW_THEN_DONE[:3])

    assert sample.completed_at is None
    assert sample.state_wait_time == timedelta(0)


def test_review_over_a_weekend_counts_working_time_only() -> None:
    # Fri 2026-09-04 -> Mon 2026-09-07 on the Mon-Fri calendar: Friday only.
    rules = replace(DEFAULT_RULES, wait_state_names=("In Review",))
    sample = _sample(
        [
            _at(EventType.CREATED, 1),
            _move(EventType.STARTED, 3, "Todo", "In Progress"),
            _move(EventType.STATE_CHANGED, 4, "In Progress", "In Review"),
            _move(EventType.COMPLETED, 7, "In Review", "Done"),
        ],
        rules,
    )

    assert sample.state_wait_time == timedelta(days=1)


def test_listed_review_lowers_flow_efficiency() -> None:
    # A 5-day cycle with 3 days in review: 1.0 unlisted, 0.4 listed.
    assert flow_efficiency([_sample(REVIEW_THEN_DONE, CALENDAR_DAYS)]) == 1.0
    assert flow_efficiency([_sample(REVIEW_THEN_DONE)]) == 0.4


def test_review_outlasting_a_blocked_label_counts_only_the_unblocked_rest() -> None:
    # Blocked days 3-5, In Review days 4-6: 3 days of wait, 2 of them blocked.
    sample = _sample(
        [
            _at(EventType.CREATED, 1),
            _move(EventType.STARTED, 2, "Todo", "In Progress"),
            _at(EventType.LABEL_ADDED, 3, "Blocked"),
            _move(EventType.STATE_CHANGED, 4, "In Progress", "In Review"),
            _at(EventType.LABEL_REMOVED, 5, "Blocked"),
            _move(EventType.COMPLETED, 6, "In Review", "Done"),
        ]
    )

    assert sample.blocked_time == timedelta(days=2)
    assert sample.state_wait_time == timedelta(days=1)
