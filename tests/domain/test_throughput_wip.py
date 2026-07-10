from datetime import UTC, datetime, timedelta

from app.domain.metrics.samples import FlowSample
from app.domain.metrics.throughput import throughput
from app.domain.metrics.wip import wip

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _sample(
    created_days_ago: int,
    started_days_ago: int | None,
    completed_days_ago: int | None,
) -> FlowSample:
    return FlowSample(
        created_at=NOW - timedelta(days=created_days_ago),
        started_at=NOW - timedelta(days=started_days_ago)
        if started_days_ago is not None
        else None,
        completed_at=NOW - timedelta(days=completed_days_ago)
        if completed_days_ago is not None
        else None,
        blocked_time=timedelta(0),
    )


def test_throughput_counts_completions_inside_window() -> None:
    samples = [
        _sample(20, 15, 5),  # inside
        _sample(60, 50, 40),  # before window
        _sample(10, 8, None),  # not completed
    ]

    assert throughput(samples, start=NOW - timedelta(days=30), end=NOW) == 1


def test_throughput_window_is_exclusive_start_inclusive_end() -> None:
    boundary = _sample(60, 50, 30)  # completed exactly at window start

    assert throughput([boundary], start=NOW - timedelta(days=30), end=NOW) == 0
    assert throughput([_sample(10, 8, 0)], start=NOW - timedelta(days=30), end=NOW) == 1


def test_wip_counts_started_but_not_completed() -> None:
    samples = [
        _sample(10, 8, None),  # in progress -> WIP
        _sample(10, None, None),  # never started -> not WIP
        _sample(10, 8, 2),  # completed -> not WIP
    ]

    assert wip(samples, at=NOW) == 1


def test_wip_ignores_items_started_after_the_instant() -> None:
    future_start = _sample(10, -1, None)  # starts tomorrow relative to NOW

    assert wip([future_start], at=NOW) == 0
