from datetime import UTC, datetime, timedelta

from app.domain.metrics.queue_touch import queue_times, touch_times
from app.domain.metrics.samples import FlowSample

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _sample(*, start_h: int, done_h: int, blocked_h: int = 0) -> FlowSample:
    return FlowSample(
        created_at=T0,
        started_at=T0 + timedelta(hours=start_h),
        completed_at=T0 + timedelta(hours=done_h),
        blocked_time=timedelta(hours=blocked_h),
    )


def test_queue_time_is_prestart_wait_plus_blocked() -> None:
    assert queue_times([_sample(start_h=4, done_h=10, blocked_h=2)]) == [timedelta(hours=6)]


def test_touch_time_is_cycle_minus_blocked() -> None:
    assert touch_times([_sample(start_h=4, done_h=10, blocked_h=2)]) == [timedelta(hours=4)]


def test_blocked_longer_than_cycle_floors_touch_at_zero() -> None:
    assert touch_times([_sample(start_h=4, done_h=6, blocked_h=5)]) == [timedelta(0)]


def test_incomplete_samples_contribute_nothing() -> None:
    unstarted = FlowSample(
        created_at=T0, started_at=None, completed_at=None, blocked_time=timedelta(0)
    )
    assert queue_times([unstarted]) == []
    assert touch_times([unstarted]) == []
