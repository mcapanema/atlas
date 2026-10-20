from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules
from app.domain.metrics.aging import compute_aging_wip
from app.domain.metrics.cycle_time import cycle_times
from app.domain.metrics.flow_efficiency import flow_efficiency, measured_cycles
from app.domain.metrics.lead_time import lead_times
from app.domain.metrics.queue_touch import queue_times, touch_times
from app.domain.metrics.samples import FlowSample, derive_flow_sample
from app.domain.work_items.entities import WorkItem
from tests.fakes import CALENDAR_DAYS

ITEM = uuid4()

# 2026-10-15 is a Thursday: 16 Fri, 17 Sat, 18 Sun, 19 Mon, 20 Tue.
THU, FRI, SAT, SUN, MON, TUE = (
    datetime(2026, 10, day, hour, tzinfo=UTC)
    for day, hour in ((15, 12), (16, 12), (17, 10), (18, 10), (19, 12), (20, 12))
)


def _sample(
    events: list[tuple[EventType, datetime]], rules: MetricRules = DEFAULT_RULES
) -> FlowSample:
    sample = derive_flow_sample(
        [Event(work_item_id=ITEM, type=t, occurred_at=at) for t, at in events], rules
    )
    assert sample is not None
    return sample


def _fri_to_mon(rules: MetricRules = DEFAULT_RULES) -> FlowSample:
    return _sample([(EventType.STARTED, FRI), (EventType.COMPLETED, MON)], rules)


def test_cycle_time_skips_the_weekend() -> None:
    assert cycle_times([_fri_to_mon()]) == [timedelta(days=1)]


def test_seven_working_days_restore_calendar_time() -> None:
    assert cycle_times([_fri_to_mon(CALENDAR_DAYS)]) == [timedelta(days=3)]


def test_lead_time_skips_the_weekend() -> None:
    sample = _sample([(EventType.CREATED, THU), (EventType.COMPLETED, MON)])

    assert lead_times([sample]) == [timedelta(days=2)]


def test_blocked_time_skips_the_weekend() -> None:
    sample = _sample(
        [
            (EventType.STARTED, THU),
            (EventType.BLOCKED, FRI),
            (EventType.UNBLOCKED, MON),
            (EventType.COMPLETED, TUE),
        ]
    )

    assert sample.blocked_time == timedelta(days=1)


def test_queue_and_touch_skip_the_weekend() -> None:
    sample = _sample(
        [(EventType.CREATED, FRI), (EventType.STARTED, MON), (EventType.COMPLETED, TUE)]
    )

    assert queue_times([sample]) == [timedelta(days=1)]
    assert touch_times([sample]) == [timedelta(days=1)]


def test_weekend_only_cycle_is_left_out_of_flow_efficiency() -> None:
    sample = _sample([(EventType.STARTED, SAT), (EventType.COMPLETED, SUN)])

    assert measured_cycles([sample]) == []
    assert flow_efficiency([sample]) is None


def test_aging_age_skips_the_weekend() -> None:
    sample = _sample([(EventType.STARTED, FRI)])
    item = WorkItem(team_id=uuid4(), title="x")

    assert compute_aging_wip([(item, sample)], now=MON).items[0].age == timedelta(days=1)


def test_each_sample_measures_on_its_own_calendar() -> None:
    assert cycle_times([_fri_to_mon(), _fri_to_mon(CALENDAR_DAYS)]) == [
        timedelta(days=1),
        timedelta(days=3),
    ]
