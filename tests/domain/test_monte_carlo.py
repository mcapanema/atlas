from datetime import UTC, datetime, timedelta

import pytest

from app.domain.forecasting.monte_carlo import (
    OutcomeBucket,
    daily_throughput_samples,
    delivery_confidence,
    simulate_days_to_complete,
    summarize_completion,
)
from app.domain.metrics.samples import FlowSample, observed_history_days

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
    with pytest.raises(ValueError, match="remaining must be >= 0"):
        simulate_days_to_complete([1], remaining=-1)


def test_summarize_completion_percentiles_and_outcome_histogram() -> None:
    forecast = summarize_completion([10] * 90 + [20] * 10, remaining=5)

    assert forecast.remaining == 5
    assert forecast.trials == 100
    assert forecast.p50_days == 10
    assert forecast.p85_days == 10
    assert forecast.p95_days == 20
    assert forecast.outcomes == (
        OutcomeBucket(days=10, trials=90),
        OutcomeBucket(days=20, trials=10),
    )


def test_delivery_confidence_is_the_share_of_trials_within_target() -> None:
    trial_days = [5, 10, 15, 20]

    assert delivery_confidence(trial_days, within_days=12) == 0.5
    assert delivery_confidence(trial_days, within_days=4) == 0.0
    assert delivery_confidence(trial_days, within_days=20) == 1.0


def _created(days_ago: float) -> FlowSample:
    return FlowSample(
        created_at=NOW - timedelta(days=days_ago),
        started_at=None,
        completed_at=None,
        blocked_time=timedelta(0),
    )


def test_observed_history_starts_at_the_scopes_first_item() -> None:
    # First seen 9.5 days ago: 10 observable days (the partial first day counts).
    assert observed_history_days([_created(9.5)], end=NOW, days=90) == 10


def test_a_ramping_scope_keeps_its_build_up_before_the_first_completion() -> None:
    # A project fills up for 40 days before anything finishes: those are real
    # zero-throughput days, not untracked ones (anchoring at the first
    # completion alone read 3 days and forecast optimistically).
    scope = [*[_created(40) for _ in range(19)], _completed(2)]
    assert observed_history_days(scope, end=NOW, days=90) == 41


def test_an_old_moved_in_item_does_not_stretch_the_observed_history() -> None:
    # Audit 2026-10-13: an issue created 15 months before the team, moved
    # in and still open, made 41 pre-team days count as zero-throughput days.
    scope = [_created(470), *[_completed(48.5 - i) for i in range(19)]]
    assert observed_history_days(scope, end=NOW, days=90) == 49


def test_observed_history_is_capped_at_the_requested_window() -> None:
    assert observed_history_days([_completed(200)], end=NOW, days=90) == 90


def test_observed_history_without_completions_starts_at_the_items() -> None:
    assert observed_history_days([_created(5)], end=NOW, days=90) == 6
    assert observed_history_days([], end=NOW, days=90) == 90


def test_observed_history_is_at_least_one_day() -> None:
    assert observed_history_days([_completed(-2)], end=NOW, days=90) == 1


def test_tracked_since_drops_items_older_than_it() -> None:
    # A 3-item scope: one moved-in item outweighs the percentile (it read 90
    # days). The team's tracked-since date says when tracking began.
    scope = [_created(470), _created(9.5), _completed(5)]
    assert observed_history_days(scope, end=NOW, days=90) == 90
    since = NOW - timedelta(days=30)
    assert observed_history_days(scope, end=NOW, days=90, tracked_since=since) == 10


def test_tracked_since_is_a_floor_a_later_project_starts_at_its_own_items() -> None:
    # The team's date bounds a project's history; it doesn't set its start.
    scope = [_created(20), _completed(3)]
    since = NOW - timedelta(days=60)
    assert observed_history_days(scope, end=NOW, days=90, tracked_since=since) == 21


def test_tracked_since_with_nothing_after_it_starts_at_the_date() -> None:
    since = NOW - timedelta(days=10)
    assert observed_history_days([_created(470)], end=NOW, days=90, tracked_since=since) == 11
    assert observed_history_days([], end=NOW, days=90, tracked_since=since) == 11


def test_a_future_tracked_since_still_leaves_one_day() -> None:
    since = NOW + timedelta(days=5)
    assert observed_history_days([_completed(2)], end=NOW, days=90, tracked_since=since) == 1
