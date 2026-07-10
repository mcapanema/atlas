from datetime import UTC, datetime, timedelta

from app.domain.metrics.cycle_time import cycle_times
from app.domain.metrics.lead_time import lead_times
from app.domain.metrics.samples import FlowSample

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


def test_lead_times_measure_creation_to_completion() -> None:
    assert lead_times([_sample(10, 8, 2)]) == [timedelta(days=8)]


def test_lead_times_skip_uncompleted_samples() -> None:
    assert lead_times([_sample(10, 8, None), _sample(5, None, None)]) == []


def test_cycle_times_measure_start_to_completion() -> None:
    assert cycle_times([_sample(10, 8, 2)]) == [timedelta(days=6)]


def test_cycle_times_skip_unstarted_or_uncompleted_samples() -> None:
    completed_without_start = _sample(10, None, 2)
    still_in_progress = _sample(10, 8, None)

    assert cycle_times([completed_without_start, still_in_progress]) == []


def test_empty_input_yields_empty_lists() -> None:
    assert lead_times([]) == []
    assert cycle_times([]) == []
