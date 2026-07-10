from datetime import UTC, datetime, timedelta

from app.domain.metrics.blocked_time import total_blocked_time
from app.domain.metrics.flow_efficiency import flow_efficiency
from app.domain.metrics.samples import FlowSample

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _sample(
    started_days_ago: int | None,
    completed_days_ago: int | None,
    blocked_days: int = 0,
) -> FlowSample:
    return FlowSample(
        created_at=NOW - timedelta(days=30),
        started_at=NOW - timedelta(days=started_days_ago)
        if started_days_ago is not None
        else None,
        completed_at=NOW - timedelta(days=completed_days_ago)
        if completed_days_ago is not None
        else None,
        blocked_time=timedelta(days=blocked_days),
    )


def test_total_blocked_time_sums_samples() -> None:
    assert total_blocked_time([_sample(10, 2, 3), _sample(8, 1, 1)]) == timedelta(days=4)


def test_total_blocked_time_of_nothing_is_zero() -> None:
    assert total_blocked_time([]) == timedelta(0)


def test_flow_efficiency_penalizes_blocked_time() -> None:
    # cycle 10d, blocked 5d -> 0.5
    assert flow_efficiency([_sample(10, 0, 5)]) == 0.5


def test_flow_efficiency_averages_completed_samples() -> None:
    # 0.5 and 1.0 -> 0.75
    assert flow_efficiency([_sample(10, 0, 5), _sample(4, 0, 0)]) == 0.75


def test_flow_efficiency_ignores_uncompleted_and_unstarted_samples() -> None:
    assert flow_efficiency([_sample(10, None, 2), _sample(None, 2, 0)]) is None


def test_flow_efficiency_clamps_blocked_time_to_cycle() -> None:
    # blocked longer than cycle (block spanned pre-start queue time) -> floor at 0.0
    assert flow_efficiency([_sample(2, 0, 5)]) == 0.0


def test_flow_efficiency_none_without_data() -> None:
    assert flow_efficiency([]) is None
