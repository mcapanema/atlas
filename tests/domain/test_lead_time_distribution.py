from datetime import UTC, datetime, timedelta

from app.domain.metrics.distribution import (
    DurationBin,
    compute_lead_time_distribution,
    duration_bins,
)
from app.domain.metrics.samples import FlowSample

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _completed_sample(created_days_ago: int, completed_days_ago: int) -> FlowSample:
    return FlowSample(
        created_at=NOW - timedelta(days=created_days_ago),
        started_at=None,
        completed_at=NOW - timedelta(days=completed_days_ago),
        blocked_time=timedelta(0),
    )


def test_duration_bins_bin_by_whole_days_including_empty_bins() -> None:
    bins = duration_bins([timedelta(hours=6), timedelta(days=2, hours=1)])

    assert bins == [
        DurationBin(start_days=0, end_days=1, count=1),
        DurationBin(start_days=1, end_days=2, count=0),
        DurationBin(start_days=2, end_days=3, count=1),
    ]


def test_duration_bins_of_nothing_is_empty() -> None:
    assert duration_bins([]) == []


def test_distribution_only_counts_window_completions() -> None:
    dist = compute_lead_time_distribution(
        [_completed_sample(10, 5), _completed_sample(200, 100)], now=NOW
    )

    assert dist.window_start == NOW - timedelta(days=90)
    assert dist.window_end == NOW
    assert sum(b.count for b in dist.bins) == 1
    assert dist.bins[5].count == 1  # the in-window item's 5-day lead time


def test_distribution_of_empty_scope_has_no_bins() -> None:
    dist = compute_lead_time_distribution([], now=NOW)

    assert dist.bins == ()
