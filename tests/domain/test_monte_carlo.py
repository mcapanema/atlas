from datetime import UTC, datetime, timedelta

import pytest

from app.domain.forecasting.monte_carlo import (
    OutcomeBucket,
    daily_throughput_samples,
    delivery_confidence,
    simulate_days_to_complete,
    summarize_completion,
)
from app.domain.metrics.samples import FlowSample

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _completed(days_ago: float) -> FlowSample:
    return FlowSample(
        created_at=NOW - timedelta(days=days_ago + 1),
        started_at=None,
        completed_at=NOW - timedelta(days=days_ago),
        blocked_time=timedelta(0),
    )


def test_daily_samples_bucket_completions_by_trailing_day_with_zeros() -> None:
    samples = [_completed(0), _completed(0.5), _completed(2)]

    assert daily_throughput_samples(samples, end=NOW, days=4) == [2, 0, 1, 0]


def test_daily_samples_exclude_completions_outside_the_window() -> None:
    assert daily_throughput_samples([_completed(5)], end=NOW, days=5) == [0] * 5


def test_daily_samples_ignore_uncompleted_items() -> None:
    open_item = FlowSample(
        created_at=NOW - timedelta(days=3),
        started_at=NOW - timedelta(days=2),
        completed_at=None,
        blocked_time=timedelta(0),
    )

    assert daily_throughput_samples([open_item], end=NOW, days=3) == [0, 0, 0]


def test_constant_throughput_gives_an_exact_forecast() -> None:
    assert simulate_days_to_complete([1], remaining=10, trials=100) == [10] * 100


def test_seeded_simulation_is_deterministic() -> None:
    daily = [0, 0, 1, 2, 0, 3, 1]

    first = simulate_days_to_complete(daily, remaining=20, trials=500, seed=42)
    second = simulate_days_to_complete(daily, remaining=20, trials=500, seed=42)

    assert first == second


def test_no_historical_throughput_cannot_forecast() -> None:
    assert simulate_days_to_complete([0, 0, 0], remaining=5) is None


def test_zero_remaining_completes_in_zero_days() -> None:
    assert simulate_days_to_complete([1], remaining=0, trials=10) == [0] * 10


def test_negative_remaining_is_rejected() -> None:
    with pytest.raises(ValueError):
        simulate_days_to_complete([1], remaining=-1)


def test_summarize_completion_percentiles_and_outcome_histogram() -> None:
    forecast = summarize_completion([10] * 90 + [20] * 10, remaining=5)

    assert forecast.remaining == 5
    assert forecast.trials == 100
    assert forecast.p50_days == 10
    assert forecast.p85_days == 10
    assert forecast.p95_days == 20
    assert forecast.outcomes == [
        OutcomeBucket(days=10, trials=90),
        OutcomeBucket(days=20, trials=10),
    ]


def test_delivery_confidence_is_the_share_of_trials_within_target() -> None:
    trial_days = [5, 10, 15, 20]

    assert delivery_confidence(trial_days, within_days=12) == 0.5
    assert delivery_confidence(trial_days, within_days=4) == 0.0
    assert delivery_confidence(trial_days, within_days=20) == 1.0
