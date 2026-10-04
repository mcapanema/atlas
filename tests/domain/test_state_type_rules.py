# tests/domain/test_state_type_rules.py
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import MetricRules
from app.domain.metrics.lead_time import lead_times
from app.domain.metrics.queue_touch import queue_times
from app.domain.metrics.samples import derive_flow_sample, in_progress, state_type_at
from app.domain.work_items.entities import StateType

ITEM = uuid4()
T = StateType


def _day(day: int) -> datetime:
    return datetime(2026, 9, day, tzinfo=UTC)


def _on(type_: EventType, day: int) -> Event:
    return Event(work_item_id=ITEM, type=type_, occurred_at=_day(day))


def _moved(
    from_type: StateType, to_type: StateType, day: int, type_: EventType = EventType.STATE_CHANGED
) -> Event:
    return Event(
        work_item_id=ITEM,
        type=type_,
        occurred_at=_day(day),
        from_state_type=from_type,
        to_state_type=to_type,
    )


DONE_THEN_TODO = [
    _on(EventType.CREATED, 1),
    _moved(T.UNSTARTED, T.STARTED, 2, EventType.STARTED),
    _moved(T.STARTED, T.COMPLETED, 4, EventType.COMPLETED),
    _moved(T.COMPLETED, T.UNSTARTED, 6),
]
REOPENED = MetricRules(done_then_reopened="reopened")


def test_done_to_todo_stays_delivered_by_default() -> None:
    sample = derive_flow_sample(DONE_THEN_TODO)

    assert sample is not None
    assert sample.completed_at == _day(4)


def test_done_to_todo_reopens_under_the_rule_as_open_not_wip() -> None:
    sample = derive_flow_sample(DONE_THEN_TODO, REOPENED)

    assert sample is not None
    assert (sample.completed_at, sample.stopped_at) == (None, _day(6))
    assert not in_progress(sample, _day(7))


def test_done_to_deployed_is_not_a_reopen() -> None:
    events = [*DONE_THEN_TODO[:3], _moved(T.COMPLETED, T.COMPLETED, 6)]

    sample = derive_flow_sample(events, REOPENED)

    assert sample is not None
    assert sample.completed_at == _day(4)


def test_a_restart_after_a_done_reopen_keeps_the_clock() -> None:
    events = [
        *DONE_THEN_TODO,
        _moved(T.UNSTARTED, T.STARTED, 8, EventType.STARTED),
        _moved(T.STARTED, T.COMPLETED, 9, EventType.COMPLETED),
    ]
    rules = MetricRules(done_then_reopened="reopened", restart_clock_after_move_back=True)

    sample = derive_flow_sample(events, rules)

    assert sample is not None
    assert (sample.started_at, sample.completed_at) == (_day(2), _day(9))


CANCELED_THEN_TODO = [
    _on(EventType.CREATED, 1),
    _moved(T.UNSTARTED, T.STARTED, 2, EventType.STARTED),
    _moved(T.STARTED, T.CANCELED, 3),
    _on(EventType.STOPPED, 3),
    _on(EventType.CANCELED, 3),
    _moved(T.CANCELED, T.UNSTARTED, 5),
]


def test_canceled_to_todo_stays_canceled_by_default() -> None:
    sample = derive_flow_sample(CANCELED_THEN_TODO)

    assert sample is not None
    assert sample.canceled is True


def test_canceled_to_todo_reopens_under_the_rule_and_a_restart_restarts_the_clock() -> None:
    rules = MetricRules(canceled_then_reopened="reopened", restart_clock_after_move_back=True)
    reopened = derive_flow_sample(CANCELED_THEN_TODO, rules)
    restarted = derive_flow_sample(
        [*CANCELED_THEN_TODO, _moved(T.UNSTARTED, T.STARTED, 8, EventType.STARTED)], rules
    )

    assert reopened is not None
    assert restarted is not None
    assert (reopened.canceled, reopened.stopped_at) == (False, _day(3))
    assert not in_progress(reopened, _day(6))
    assert restarted.started_at == _day(8)


BORN_IN_TRIAGE = [
    _on(EventType.CREATED, 1),
    _moved(T.TRIAGE, T.BACKLOG, 3),
    _moved(T.BACKLOG, T.STARTED, 5, EventType.STARTED),
    _moved(T.STARTED, T.COMPLETED, 9, EventType.COMPLETED),
]
TRIAGE_EXIT = MetricRules(lead_time_start="triage_exit")


def test_lead_time_starts_at_creation_by_default() -> None:
    sample = derive_flow_sample(BORN_IN_TRIAGE)

    assert sample is not None
    assert sample.arrived_at == _day(1)
    assert lead_times([sample]) == [timedelta(days=8)]


def test_lead_and_queue_time_start_at_triage_exit_under_the_rule() -> None:
    sample = derive_flow_sample(BORN_IN_TRIAGE, TRIAGE_EXIT)

    assert sample is not None
    assert sample.arrived_at == _day(3)
    assert lead_times([sample]) == [timedelta(days=6)]
    assert queue_times([sample]) == [timedelta(days=2)]
    assert sample.created_at == _day(1)  # creation itself is unchanged


def test_an_item_never_in_triage_arrives_at_creation() -> None:
    events = [_on(EventType.CREATED, 1), _moved(T.BACKLOG, T.STARTED, 4, EventType.STARTED)]

    sample = derive_flow_sample(events, TRIAGE_EXIT)

    assert sample is not None
    assert sample.arrived_at == _day(1)


def test_triage_straight_to_started_arrives_at_the_start() -> None:
    events = [_on(EventType.CREATED, 1), _moved(T.TRIAGE, T.STARTED, 4, EventType.STARTED)]

    sample = derive_flow_sample(events, TRIAGE_EXIT)

    assert sample is not None
    assert sample.arrived_at == sample.started_at == _day(4)


def _assert_arrives_at_creation(events: list[Event]) -> None:
    sample = derive_flow_sample(events, TRIAGE_EXIT)

    assert sample is not None
    assert sample.arrived_at == _day(1)
    assert all(t >= timedelta(0) for t in [*lead_times([sample]), *queue_times([sample])])


def test_a_triage_exit_after_done_is_ignored() -> None:
    _assert_arrives_at_creation(
        [
            _on(EventType.CREATED, 1),
            _moved(T.UNSTARTED, T.STARTED, 2, EventType.STARTED),
            _moved(T.STARTED, T.COMPLETED, 3, EventType.COMPLETED),
            _moved(T.COMPLETED, T.TRIAGE, 4),
            _moved(T.TRIAGE, T.UNSTARTED, 5),
        ]
    )


def test_a_triage_exit_after_the_first_start_is_ignored() -> None:
    _assert_arrives_at_creation(
        [
            _on(EventType.CREATED, 1),
            _moved(T.UNSTARTED, T.STARTED, 3, EventType.STARTED),
            _moved(T.STARTED, T.TRIAGE, 4),
            _moved(T.TRIAGE, T.STARTED, 5, EventType.STARTED),
            _moved(T.STARTED, T.COMPLETED, 6, EventType.COMPLETED),
        ]
    )


REOPEN_RESTART = MetricRules(done_then_reopened="reopened", restart_clock_after_move_back=True)


def test_a_start_after_reopen_then_cancel_restarts_the_clock() -> None:
    events = [
        _on(EventType.CREATED, 1),
        _moved(T.UNSTARTED, T.STARTED, 2, EventType.STARTED),
        _moved(T.STARTED, T.COMPLETED, 3, EventType.COMPLETED),
        _moved(T.COMPLETED, T.UNSTARTED, 4),
        _on(EventType.CANCELED, 5),
        _moved(T.UNSTARTED, T.STARTED, 6, EventType.STARTED),
    ]

    sample = derive_flow_sample(events, REOPEN_RESTART)

    assert sample is not None
    assert sample.started_at == _day(6)


def test_a_start_after_repeated_done_reopens_keeps_the_clock() -> None:
    events = [
        _on(EventType.CREATED, 1),
        _moved(T.UNSTARTED, T.STARTED, 2, EventType.STARTED),
        _moved(T.STARTED, T.COMPLETED, 3, EventType.COMPLETED),
        _moved(T.COMPLETED, T.UNSTARTED, 4),
        _moved(T.UNSTARTED, T.COMPLETED, 5, EventType.COMPLETED),
        _moved(T.COMPLETED, T.UNSTARTED, 6),
        _moved(T.UNSTARTED, T.STARTED, 7, EventType.STARTED),
    ]

    sample = derive_flow_sample(events, REOPEN_RESTART)

    assert sample is not None
    assert sample.started_at == _day(2)


def test_state_type_at_reads_typed_transitions() -> None:
    assert state_type_at(BORN_IN_TRIAGE, _day(2), T.COMPLETED) is T.TRIAGE  # before the first
    assert state_type_at(BORN_IN_TRIAGE, _day(4), T.COMPLETED) is T.BACKLOG
    assert state_type_at(BORN_IN_TRIAGE, _day(5), T.COMPLETED) is T.STARTED  # at the instant
    assert state_type_at(BORN_IN_TRIAGE, None, T.COMPLETED) is T.COMPLETED  # now: stored
    untyped = [_on(EventType.CREATED, 1)]
    assert state_type_at(untyped, _day(2), T.BACKLOG) is T.BACKLOG
    assert state_type_at(untyped, _day(2), None) is None
