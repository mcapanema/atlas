from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from app.domain.events.entities import Event, EventType
from app.domain.metrics.cfd import DailyFlowCount, daily_flow_counts


def _event(type_: EventType, day: int, item_id: UUID) -> Event:
    return Event(
        work_item_id=item_id, type=type_, occurred_at=datetime(2026, 7, day, 12, tzinfo=UTC)
    )


def test_counts_items_per_phase_per_day() -> None:
    a, b = uuid4(), uuid4()
    streams = [
        [
            _event(EventType.CREATED, 1, a),
            _event(EventType.STARTED, 2, a),
            _event(EventType.COMPLETED, 4, a),
        ],
        [_event(EventType.CREATED, 3, b)],
    ]

    counts = daily_flow_counts(
        streams,
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 5, 23, 0, tzinfo=UTC),
    )

    assert counts == [
        DailyFlowCount(day=date(2026, 7, 1), todo=1, in_progress=0, done=0),
        DailyFlowCount(day=date(2026, 7, 2), todo=0, in_progress=1, done=0),
        DailyFlowCount(day=date(2026, 7, 3), todo=1, in_progress=1, done=0),
        DailyFlowCount(day=date(2026, 7, 4), todo=1, in_progress=0, done=1),
        DailyFlowCount(day=date(2026, 7, 5), todo=1, in_progress=0, done=1),
    ]


def test_reopened_item_counts_in_progress_after_but_done_before() -> None:
    a = uuid4()
    stream = [
        _event(EventType.CREATED, 1, a),
        _event(EventType.STARTED, 1, a),
        _event(EventType.COMPLETED, 2, a),
        _event(EventType.STARTED, 4, a),  # reopen
    ]

    counts = daily_flow_counts(
        [stream],
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 4, 23, 0, tzinfo=UTC),
    )

    # History is not rewritten: days 2-3 stay done, day 4 is in progress again.
    assert counts[1] == DailyFlowCount(day=date(2026, 7, 2), todo=0, in_progress=0, done=1)
    assert counts[2] == DailyFlowCount(day=date(2026, 7, 3), todo=0, in_progress=0, done=1)
    assert counts[3] == DailyFlowCount(day=date(2026, 7, 4), todo=0, in_progress=1, done=0)


def test_no_streams_yields_zero_rows_for_every_day() -> None:
    counts = daily_flow_counts(
        [],
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 3, tzinfo=UTC),
    )

    assert len(counts) == 3
    assert all(c.todo == c.in_progress == c.done == 0 for c in counts)
