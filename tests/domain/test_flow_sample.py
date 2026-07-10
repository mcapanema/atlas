from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.metrics.samples import derive_flow_sample

WORK_ITEM_ID = uuid4()


def _event(
    type_: EventType, day: int, from_state: str | None = None, to_state: str | None = None
) -> Event:
    return Event(
        work_item_id=WORK_ITEM_ID,
        type=type_,
        occurred_at=datetime(2026, 6, day, tzinfo=UTC),
        from_state=from_state,
        to_state=to_state,
    )


def test_no_events_returns_none() -> None:
    assert derive_flow_sample([]) is None


def test_full_lifecycle_yields_all_timestamps() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 3, from_state="Backlog", to_state="In Progress"),
            _event(EventType.COMPLETED, 8, from_state="In Progress", to_state="Done"),
        ]
    )

    assert sample is not None
    assert sample.created_at == datetime(2026, 6, 1, tzinfo=UTC)
    assert sample.started_at == datetime(2026, 6, 3, tzinfo=UTC)
    assert sample.completed_at == datetime(2026, 6, 8, tzinfo=UTC)
    assert sample.blocked_time == timedelta(0)


def test_unstarted_item_has_no_started_or_completed() -> None:
    sample = derive_flow_sample([_event(EventType.CREATED, 1)])

    assert sample is not None
    assert sample.started_at is None
    assert sample.completed_at is None


def test_reopened_item_is_not_completed() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.COMPLETED, 3),
            _event(EventType.STARTED, 5),
        ]
    )

    assert sample is not None
    assert sample.completed_at is None


def test_recompleted_item_uses_last_completion_and_first_start() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.COMPLETED, 3),
            _event(EventType.STARTED, 5),
            _event(EventType.COMPLETED, 9),
        ]
    )

    assert sample is not None
    assert sample.started_at == datetime(2026, 6, 2, tzinfo=UTC)
    assert sample.completed_at == datetime(2026, 6, 9, tzinfo=UTC)


def test_blocked_time_sums_closed_periods() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.BLOCKED, 3),
            _event(EventType.UNBLOCKED, 5),
            _event(EventType.COMPLETED, 8),
        ]
    )

    assert sample is not None
    assert sample.blocked_time == timedelta(days=2)


def test_open_blocked_period_clamps_to_completion() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.BLOCKED, 3),
            _event(EventType.COMPLETED, 6),
        ]
    )

    assert sample is not None
    assert sample.blocked_time == timedelta(days=3)


def test_open_blocked_period_without_completion_is_not_counted() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.BLOCKED, 3),
        ]
    )

    assert sample is not None
    assert sample.blocked_time == timedelta(0)
