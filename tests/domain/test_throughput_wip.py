from datetime import UTC, datetime, timedelta

from app.domain.metrics.samples import FlowSample
from app.domain.metrics.throughput import bucketed_throughput, throughput
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


def test_bucketed_throughput_supports_daily_buckets() -> None:
    end = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)

    def completed(offset: timedelta) -> FlowSample:
        return FlowSample(
            created_at=end - offset - timedelta(days=1),
            started_at=None,
            completed_at=end - offset,
            blocked_time=timedelta(0),
        )

    samples = [
        completed(timedelta(days=1)),
        completed(timedelta(hours=2)),
        completed(timedelta(hours=1)),
    ]

    buckets = bucketed_throughput(samples, end=end, count=3, bucket_days=1)

    assert [b.completed for b in buckets] == [0, 1, 2]
    assert buckets[-1].end == end
    assert buckets[-1].start == end - timedelta(days=1)
    assert buckets[0].start == end - timedelta(days=3)


def test_bucketed_throughput_weekly_buckets_completions_oldest_first() -> None:
    from app.domain.metrics.throughput import ThroughputBucket

    end = datetime(2026, 7, 10, tzinfo=UTC)

    def completed(days_ago: int) -> FlowSample:
        return FlowSample(
            created_at=end - timedelta(days=days_ago + 1),
            started_at=None,
            completed_at=end - timedelta(days=days_ago),
            blocked_time=timedelta(0),
        )

    samples = [completed(1), completed(2), completed(10)]

    buckets = bucketed_throughput(samples, end=end, count=2, bucket_days=7)

    assert [b.completed for b in buckets] == [1, 2]
    assert buckets[0] == ThroughputBucket(
        start=end - timedelta(days=14), end=end - timedelta(days=7), completed=1
    )
    assert buckets[1].end == end
