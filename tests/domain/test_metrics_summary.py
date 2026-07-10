from datetime import UTC, datetime, timedelta

import pytest

from app.domain.metrics.samples import FlowSample
from app.domain.metrics.stats import percentile
from app.domain.metrics.summary import compute_team_metrics

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _sample(
    created_days_ago: int,
    started_days_ago: int | None,
    completed_days_ago: int | None,
    blocked_days: int = 0,
) -> FlowSample:
    return FlowSample(
        created_at=NOW - timedelta(days=created_days_ago),
        started_at=NOW - timedelta(days=started_days_ago)
        if started_days_ago is not None
        else None,
        completed_at=NOW - timedelta(days=completed_days_ago)
        if completed_days_ago is not None
        else None,
        blocked_time=timedelta(days=blocked_days),
    )


def test_percentile_interpolates_linearly() -> None:
    assert percentile([0.0, 10.0], 50) == 5.0
    assert percentile([0.0, 10.0], 95) == 9.5


def test_percentile_of_single_value_is_that_value() -> None:
    assert percentile([7.0], 85) == 7.0


def test_percentile_rejects_empty_input_and_bad_p() -> None:
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1.0], 0)
    with pytest.raises(ValueError):
        percentile([1.0], 100)


def test_compute_team_metrics_aggregates_the_trailing_window() -> None:
    samples = [
        _sample(20, 15, 5),  # completed in window: lead 15d, cycle 10d
        _sample(60, 50, 40),  # completed before window: excluded from aggregates
        _sample(10, 8, None),  # in progress: counts toward WIP only
    ]

    metrics = compute_team_metrics(samples, now=NOW)

    assert metrics.window_start == NOW - timedelta(days=30)
    assert metrics.window_end == NOW
    assert metrics.completed == 1
    assert metrics.wip == 1
    assert metrics.lead_time is not None
    assert metrics.lead_time.p50 == timedelta(days=15)
    assert metrics.lead_time.mean == timedelta(days=15)
    assert metrics.cycle_time is not None
    assert metrics.cycle_time.p50 == timedelta(days=10)
    assert metrics.blocked_time == timedelta(0)
    assert metrics.flow_efficiency == 1.0


def test_compute_team_metrics_includes_blocked_time_of_window_completions() -> None:
    metrics = compute_team_metrics([_sample(20, 10, 0, blocked_days=5)], now=NOW)

    assert metrics.blocked_time == timedelta(days=5)
    assert metrics.flow_efficiency == 0.5


def test_compute_team_metrics_with_no_samples_is_empty() -> None:
    metrics = compute_team_metrics([], now=NOW)

    assert metrics.completed == 0
    assert metrics.wip == 0
    assert metrics.lead_time is None
    assert metrics.cycle_time is None
    assert metrics.blocked_time == timedelta(0)
    assert metrics.flow_efficiency is None
