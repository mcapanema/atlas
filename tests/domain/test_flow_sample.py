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


def test_blocked_time_stops_at_completion() -> None:
    # Blocked label removed only after Done: the post-completion tail is not
    # blocked work. Uncapped, it can exceed the cycle and zero out efficiency.
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.BLOCKED, 4),
            _event(EventType.COMPLETED, 6),
            _event(EventType.UNBLOCKED, 9),
        ]
    )

    assert sample is not None
    assert sample.blocked_time == timedelta(days=2)


def test_blocked_time_before_start_is_not_counted() -> None:
    # Pre-start wait is already queue time; counting a blocked label there
    # too would double-count it in queue time.
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.BLOCKED, 2),
            _event(EventType.STARTED, 3),
            _event(EventType.UNBLOCKED, 5),
            _event(EventType.COMPLETED, 8),
        ]
    )

    assert sample is not None
    assert sample.blocked_time == timedelta(days=2)


def test_move_back_out_of_progress_stops_the_item() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.STOPPED, 5),
        ]
    )

    assert sample is not None
    assert sample.started_at == datetime(2026, 6, 2, tzinfo=UTC)
    assert sample.stopped_at == datetime(2026, 6, 5, tzinfo=UTC)
    assert sample.canceled is False
    assert sample.completed_at is None


def test_restart_after_move_back_keeps_the_first_start() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.STOPPED, 5),
            _event(EventType.STARTED, 9),
        ]
    )

    assert sample is not None
    assert sample.started_at == datetime(2026, 6, 2, tzinfo=UTC)  # cycle runs from first start
    assert sample.stopped_at is None


def test_cancel_closes_an_uncompleted_item() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.CANCELED, 6),
        ]
    )

    assert sample is not None
    assert sample.canceled is True
    assert sample.stopped_at == datetime(2026, 6, 6, tzinfo=UTC)
    assert sample.completed_at is None


def test_cancel_after_move_back_keeps_the_move_back_time() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.STOPPED, 4),
            _event(EventType.CANCELED, 7),
        ]
    )

    assert sample is not None
    assert sample.canceled is True
    assert sample.stopped_at == datetime(2026, 6, 4, tzinfo=UTC)


def test_cancel_after_done_stays_delivered() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.COMPLETED, 5),
            _event(EventType.CANCELED, 7),
        ]
    )

    assert sample is not None
    assert sample.completed_at == datetime(2026, 6, 5, tzinfo=UTC)
    assert sample.canceled is False
    assert sample.stopped_at is None


def test_restart_after_cancel_reopens_and_a_second_cancel_closes_again() -> None:
    reopened = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.CANCELED, 4),
            _event(EventType.STARTED, 6),
        ]
    )
    recanceled = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 2),
            _event(EventType.CANCELED, 4),
            _event(EventType.STARTED, 6),
            _event(EventType.CANCELED, 9),
        ]
    )

    assert reopened is not None
    assert recanceled is not None
    assert reopened.canceled is False
    assert reopened.stopped_at is None
    assert recanceled.canceled is True
    assert recanceled.stopped_at == datetime(2026, 6, 9, tzinfo=UTC)


def test_completion_after_cancel_counts_as_delivered() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.CANCELED, 3),
            _event(EventType.COMPLETED, 5),
        ]
    )

    assert sample is not None
    assert sample.completed_at == datetime(2026, 6, 5, tzinfo=UTC)
    assert sample.canceled is False
    assert sample.stopped_at is None


def test_same_instant_start_and_completion_reads_completed() -> None:
    # Linear automations can write Todo -> In Progress and In Progress -> Done
    # with one timestamp; storage order must not decide the outcome.
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.COMPLETED, 3),
            _event(EventType.STARTED, 3),
        ]
    )

    assert sample is not None
    assert sample.started_at == datetime(2026, 6, 3, tzinfo=UTC)
    assert sample.completed_at == datetime(2026, 6, 3, tzinfo=UTC)


def test_stop_landing_after_the_cancel_keeps_the_item_canceled() -> None:
    # Pins fold/CFD agreement for Linear's canceledAt-before-history skew.
    t = datetime(2026, 6, 5, tzinfo=UTC)
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 3),
            Event(work_item_id=WORK_ITEM_ID, type=EventType.CANCELED, occurred_at=t),
            Event(
                work_item_id=WORK_ITEM_ID,
                type=EventType.STOPPED,
                occurred_at=t + timedelta(milliseconds=100),
            ),
        ]
    )

    assert sample is not None
    assert sample.canceled is True
    assert sample.stopped_at == t


def test_completed_at_creation_without_a_start_is_born_done() -> None:
    sample = derive_flow_sample([_event(EventType.CREATED, 1), _event(EventType.COMPLETED, 1)])

    assert sample is not None
    assert sample.born_done
    assert sample.completed_at == datetime(2026, 6, 1, tzinfo=UTC)


def test_lone_completion_without_a_created_event_is_not_born_done() -> None:
    # A completion recorded without its creation: creation unknown, not born done.
    sample = derive_flow_sample([_event(EventType.COMPLETED, 1)])

    assert sample is not None
    assert not sample.born_done
    assert sample.completed_at == datetime(2026, 6, 1, tzinfo=UTC)


def test_backfilled_created_done_beside_a_later_synthesized_completion_is_born_done() -> None:
    # A re-sync adds the creation-instant COMPLETED to items that already
    # carry sync's completedAt-stamped one, a few ms after creation.
    synthesized = Event(
        work_item_id=WORK_ITEM_ID,
        type=EventType.COMPLETED,
        occurred_at=datetime(2026, 6, 1, 0, 0, 0, 250_000, tzinfo=UTC),
    )
    sample = derive_flow_sample(
        [_event(EventType.CREATED, 1), synthesized, _event(EventType.COMPLETED, 1)]
    )

    assert sample is not None
    assert sample.born_done


def test_created_done_then_restarted_is_flow_not_born_done() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.COMPLETED, 1),
            _event(EventType.STARTED, 3, from_state="Done", to_state="In Progress"),
            _event(EventType.COMPLETED, 5, from_state="In Progress", to_state="Done"),
        ]
    )

    assert sample is not None
    assert not sample.born_done
    assert sample.started_at == datetime(2026, 6, 3, tzinfo=UTC)
    assert sample.completed_at == datetime(2026, 6, 5, tzinfo=UTC)


def test_completion_after_creation_is_not_born_done() -> None:
    sample = derive_flow_sample([_event(EventType.CREATED, 1), _event(EventType.COMPLETED, 2)])

    assert sample is not None
    assert not sample.born_done


def test_start_and_completion_at_creation_is_not_born_done() -> None:
    sample = derive_flow_sample(
        [
            _event(EventType.CREATED, 1),
            _event(EventType.STARTED, 1),
            _event(EventType.COMPLETED, 1),
        ]
    )

    assert sample is not None
    assert not sample.born_done
