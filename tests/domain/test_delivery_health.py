from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import MetricRules
from app.domain.metrics.health import HealthComponent, compute_delivery_health

NOW = datetime(2026, 7, 10, tzinfo=UTC)

# These tests pin component mechanics on tiny scopes, not the evidence floor
# (tests/domain/test_health_min_sample.py covers that).
ANY_SAMPLE = MetricRules(health_min_sample=1)


def _stream(*steps: tuple[EventType, int]) -> list[Event]:
    item_id = uuid4()
    return [
        Event(work_item_id=item_id, type=type_, occurred_at=NOW - timedelta(days=days))
        for type_, days in steps
    ]


def test_empty_scope_has_no_score() -> None:
    health = compute_delivery_health([], now=NOW)

    assert health.score is None
    assert health.band is None
    assert health.components == ()


def test_healthy_scope_scores_high_with_the_default_components() -> None:
    streams = [
        *_prior(2),  # a 2-day service level the window's 2-day cycles meet
        _stream((EventType.CREATED, 20), (EventType.STARTED, 19), (EventType.COMPLETED, 17)),
        _stream((EventType.CREATED, 10), (EventType.STARTED, 9), (EventType.COMPLETED, 7)),
        _stream((EventType.CREATED, 6), (EventType.STARTED, 5), (EventType.COMPLETED, 3)),
        _stream((EventType.CREATED, 8), (EventType.STARTED, 7), (EventType.COMPLETED, 5)),
        _stream((EventType.CREATED, 14), (EventType.STARTED, 13), (EventType.COMPLETED, 11)),
        *[_stream((EventType.CREATED, 4), (EventType.STARTED, 1)) for _ in range(5)],  # fresh WIP
        _stream((EventType.CREATED, 40)),  # backlog: history covers the window
    ]

    health = compute_delivery_health(streams, now=NOW)

    assert health.band == "healthy"
    assert health.score is not None
    assert health.score >= 70
    assert {c.name for c in health.components} == {
        "predictability",
        "flow",
        "stability",
        "risk",
    }


def test_efficiency_scores_when_its_weight_is_set() -> None:
    streams = [
        _stream((EventType.CREATED, 20), (EventType.STARTED, 19), (EventType.COMPLETED, 17)),
        _stream((EventType.CREATED, 15), (EventType.STARTED, 14), (EventType.BLOCKED, 13)),
    ]

    health = compute_delivery_health(
        streams, now=NOW, rules=MetricRules(health_min_sample=1, weight_efficiency=1.0)
    )

    assert "efficiency" in {c.name for c in health.components}


def test_open_blocked_wip_drags_risk_to_zero() -> None:
    streams = [
        _stream((EventType.CREATED, 20), (EventType.STARTED, 19), (EventType.COMPLETED, 17)),
        _stream((EventType.CREATED, 15), (EventType.STARTED, 14), (EventType.BLOCKED, 13)),
    ]

    health = compute_delivery_health(streams, now=NOW, rules=ANY_SAMPLE)

    risk = next(c for c in health.components if c.name == "risk")
    assert risk.score == 0
    assert "1 of 1" in risk.reason


def test_each_component_is_banded_by_the_scopes_cutoffs() -> None:
    # One prior 2-day cycle sets the service level; the window's 2-day cycle
    # meets it (predictability 100). One open blocked item: risk 1 of 1 -> 0.
    streams = [
        *_prior(2, count=1),
        _stream((EventType.CREATED, 20), (EventType.STARTED, 19), (EventType.COMPLETED, 17)),
        _stream((EventType.CREATED, 15), (EventType.STARTED, 14), (EventType.BLOCKED, 13)),
    ]

    health = compute_delivery_health(streams, now=NOW, rules=ANY_SAMPLE)
    bands = {c.name: c.band for c in health.components}

    assert bands["predictability"] == "healthy"
    assert bands["risk"] == "critical"
    assert all(c.band in ("healthy", "warning", "critical") for c in health.components)

    # The scope's own cutoffs decide, not built-in ones: with warning_min 0,
    # a 0 is a warning, not critical.
    lenient = compute_delivery_health(
        streams, now=NOW, rules=MetricRules(health_min_sample=1, healthy_min=1, warning_min=0)
    )
    assert next(c for c in lenient.components if c.name == "risk").band == "warning"


def test_a_component_cannot_exist_without_its_band() -> None:
    # The API's band is a required Literal: a component built anywhere but
    # scoring must not type-check, then 500 at the DTO, for lack of one.
    with pytest.raises(TypeError):
        HealthComponent(name="risk", score=50, reason="2 of 4 blocked")  # type: ignore[call-arg]


def test_components_without_data_are_omitted() -> None:
    streams = [_stream((EventType.CREATED, 5), (EventType.STARTED, 4))]

    health = compute_delivery_health(streams, now=NOW, rules=ANY_SAMPLE)

    names = {c.name for c in health.components}
    assert "predictability" not in names  # nothing completed in window
    assert "stability" not in names
    assert "risk" in names  # one unblocked, un-aged in-progress item -> score 100


def test_canceled_blocked_item_is_not_in_progress_risk() -> None:
    streams = [
        _stream((EventType.CREATED, 20), (EventType.STARTED, 19), (EventType.COMPLETED, 17)),
        _stream(
            (EventType.CREATED, 15),
            (EventType.STARTED, 14),
            (EventType.BLOCKED, 13),
            (EventType.CANCELED, 12),
        ),
        _stream((EventType.CREATED, 4), (EventType.STARTED, 1)),  # fresh WIP, age 1d < p85 2d
    ]

    health = compute_delivery_health(streams, now=NOW, rules=ANY_SAMPLE)

    risk = next(c for c in health.components if c.name == "risk")
    assert risk.score == 100
    assert "0 of 1" in risk.reason


def test_a_scope_tracked_for_part_of_the_window_has_no_flow_trend() -> None:
    # The live Forward Deployment Squad case (2026-10-09): first synced 11
    # days into a 30-day window, it read "throughput grew from 0 to 95" -> 100.
    streams = [
        _stream((EventType.CREATED, 11), (EventType.STARTED, 10), (EventType.COMPLETED, days))
        for days in (9, 7, 5, 3, 1)
    ]

    health = compute_delivery_health(streams, now=NOW)

    assert "flow" not in {c.name for c in health.components}


def test_stability_reads_weeks_of_throughput_over_the_tracked_history() -> None:
    # Tracked 11 days (first event 10 days ago, partial day counts): 5
    # completions = 3.18/week, WIP 5 = 1.57 weeks -> 86. Over the full 30
    # days it read 4.29 weeks -> 18.
    streams = [
        *[
            _stream((EventType.CREATED, 10), (EventType.STARTED, 9), (EventType.COMPLETED, d))
            for d in (8, 6, 4, 3, 2)
        ],
        *[_stream((EventType.CREATED, 4), (EventType.STARTED, 1)) for _ in range(5)],
    ]

    health = compute_delivery_health(streams, now=NOW)

    stability = next(c for c in health.components if c.name == "stability")
    assert stability.score == 86
    assert stability.reason == "WIP equals 1.6 weeks of throughput"


def _hours(started_h: float, completed_h: float) -> list[Event]:
    item_id = uuid4()
    return [
        Event(work_item_id=item_id, type=EventType.CREATED, occurred_at=NOW - timedelta(days=150)),
        Event(
            work_item_id=item_id,
            type=EventType.STARTED,
            occurred_at=NOW - timedelta(hours=started_h),
        ),
        Event(
            work_item_id=item_id,
            type=EventType.COMPLETED,
            occurred_at=NOW - timedelta(hours=completed_h),
        ),
    ]


def _prior(cycle_days: int, count: int = 5) -> list[list[Event]]:
    """`count` items completed 40 days ago (inside the 90 days before the window)."""
    return [
        _stream(
            (EventType.CREATED, 150),
            (EventType.STARTED, 40 + cycle_days),
            (EventType.COMPLETED, 40),
        )
        for _ in range(count)
    ]


def _window(cycle_days: int, count: int = 5) -> list[list[Event]]:
    """`count` items completed 2 days ago, inside the 30-day window."""
    return [
        _stream(
            (EventType.CREATED, 20),
            (EventType.STARTED, 2 + cycle_days),
            (EventType.COMPLETED, 2),
        )
        for _ in range(count)
    ]


def _predictability(streams: list[list[Event]]) -> HealthComponent | None:
    health = compute_delivery_health(streams, now=NOW)
    return next((c for c in health.components if c.name == "predictability"), None)


def test_a_slow_window_cannot_raise_its_own_service_level() -> None:
    # Prior 1-day cycles set the SLE; the window's 10-day cycles all miss it.
    # Were the window part of the reference, its P85 would be 10d and all hit.
    component = _predictability([*_prior(1), *_window(10)])

    assert component is not None
    assert component.score == 0
    assert component.reason.startswith("0% of 5 items finished within 1d")


def test_meeting_the_service_level_more_often_than_the_target_scores_100() -> None:
    component = _predictability([*_prior(3), *_window(1)])

    assert component is not None
    assert component.score == 100


def test_a_scope_without_prior_history_has_no_predictability() -> None:
    # Review focus 1: Forward Deployment's case. History starts inside the
    # window, so no commitment existed to meet: omitted, not 0 or 100.
    assert _predictability(_window(1, count=10)) is None


def test_completions_without_a_start_are_left_out_of_the_hit_rate() -> None:
    # Review focus 2: 5 started items all hit; 3 closed without starting have
    # no cycle time, so the rate is 5/5, not 5/8.
    never_started = [_stream((EventType.CREATED, 20), (EventType.COMPLETED, 2)) for _ in range(3)]

    component = _predictability([*_prior(3), *_window(1), *never_started])

    assert component is not None
    assert component.reason.startswith("100% of 5 items")


def test_a_sub_day_service_level_reads_in_hours() -> None:
    # Review focus 3: 6-hour prior cycles must not read "within 0d".
    prior = [_hours(40 * 24 + 6, 40 * 24) for _ in range(5)]
    window = [_hours(2 * 24 + 6, 2 * 24) for _ in range(5)]

    component = _predictability([*prior, *window])

    assert component is not None
    assert "within 6h" in component.reason
