from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.metrics.history import compute_flow_history

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def test_history_composes_daily_counts_and_weekly_throughput() -> None:
    item = uuid4()
    stream = [
        Event(work_item_id=item, type=EventType.CREATED, occurred_at=NOW - timedelta(days=9)),
        Event(work_item_id=item, type=EventType.STARTED, occurred_at=NOW - timedelta(days=6)),
        Event(work_item_id=item, type=EventType.COMPLETED, occurred_at=NOW - timedelta(days=2)),
    ]

    history = compute_flow_history([stream], now=NOW, window_days=90)

    assert history.window_end == NOW
    assert history.window_start == NOW - timedelta(days=90)
    assert len(history.days) == 91  # inclusive day range
    assert history.days[-1].done == 1
    assert len(history.weeks) == 12  # 90 // 7
    assert sum(b.completed for b in history.weeks) == 1


def test_history_for_no_streams_is_all_zeros() -> None:
    history = compute_flow_history([], now=NOW, window_days=14)

    assert len(history.days) == 15
    assert len(history.weeks) == 2
    assert all(c.todo == c.in_progress == c.done == 0 for c in history.days)
    assert all(b.completed == 0 for b in history.weeks)


def test_history_reports_the_newest_recorded_at_as_data_as_of() -> None:
    item = uuid4()
    stale = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    fresh = datetime(2026, 7, 8, 9, 0, tzinfo=UTC)
    stream = [
        Event(
            work_item_id=item,
            type=EventType.CREATED,
            occurred_at=NOW - timedelta(days=9),
            recorded_at=stale,
        ),
        Event(
            work_item_id=item,
            type=EventType.COMPLETED,
            occurred_at=NOW - timedelta(days=2),
            recorded_at=fresh,
        ),
    ]

    history = compute_flow_history([stream], now=NOW, window_days=90)

    assert history.data_as_of == fresh


def test_history_data_as_of_is_none_without_events() -> None:
    history = compute_flow_history([], now=NOW, window_days=14)

    assert history.data_as_of is None
