from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules, apply_overrides
from app.domain.metrics.aging import compute_aging_wip
from app.domain.metrics.health import compute_delivery_health
from app.domain.metrics.samples import FlowSample
from app.domain.work_items.entities import WorkItem

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _pair(
    title: str, *, started_days: int, completed_days: int | None = None
) -> tuple[WorkItem, FlowSample]:
    item = WorkItem(team_id=uuid4(), title=title, state="in_progress")
    sample = FlowSample(
        created_at=NOW - timedelta(days=started_days + 1),
        started_at=NOW - timedelta(days=started_days),
        completed_at=NOW - timedelta(days=completed_days) if completed_days is not None else None,
        blocked_time=timedelta(0),
    )
    return item, sample


OLD_SLOW = _pair("Old slow", started_days=200, completed_days=120)  # cycle 80d, 120d ago
RECENT = _pair("Recent", started_days=8, completed_days=1)  # cycle 7d
DOING = _pair("Doing", started_days=10)


def test_the_aging_history_defaults_to_90_days() -> None:
    assert DEFAULT_RULES.aging_history_days == 90


def test_the_reference_line_reads_only_recently_completed_cycles() -> None:
    # The live Audit case: all-time history put the line at 40.7d while the
    # Cycle time P85 tile on the same page read 55.8d.
    aging = compute_aging_wip([OLD_SLOW, RECENT, DOING], now=NOW)

    assert aging.cycle_time_percentile == timedelta(days=7)
    assert aging.history_days == 90
    assert aging.items[0].over_percentile is True  # 10d in progress > 7d


def test_the_reference_history_follows_the_rule() -> None:
    aging = compute_aging_wip([OLD_SLOW, RECENT, DOING], now=NOW, history_days=180)

    # p85 of 7d and 80d (inclusive) = 7 + 0.85 * 73 = 69.05d = 5,965,920s
    assert aging.cycle_time_percentile == timedelta(seconds=5_965_920)
    assert aging.items[0].over_percentile is False


def test_no_completion_inside_the_aging_history_means_no_flags() -> None:
    # The live SRE & Data case: nothing completed for 70 days.
    aging = compute_aging_wip([OLD_SLOW, DOING], now=NOW)

    assert aging.cycle_time_percentile is None
    assert aging.items[0].over_percentile is False


def _stream(*steps: tuple[EventType, int]) -> list[Event]:
    item_id = uuid4()
    return [
        Event(work_item_id=item_id, type=type_, occurred_at=NOW - timedelta(days=days))
        for type_, days in steps
    ]


def test_health_risk_reads_the_aging_line_from_the_aging_history() -> None:
    old_done = _stream((EventType.CREATED, 70), (EventType.STARTED, 69), (EventType.COMPLETED, 68))
    stuck = [_stream((EventType.CREATED, 40), (EventType.STARTED, 30)) for _ in range(5)]

    default = compute_delivery_health([old_done, *stuck], now=NOW)
    short = compute_delivery_health(
        [old_done, *stuck], now=NOW, rules=MetricRules(aging_history_days=30)
    )

    assert next(c for c in default.components if c.name == "risk").reason.startswith("5 of 5")
    # Nothing completed in the 30-day history, so the limit falls back to the
    # history itself: 30 days in progress is not *over* 30 days.
    assert next(c for c in short.components if c.name == "risk").reason.startswith("0 of 5")


def test_a_team_stalled_past_the_aging_history_still_reads_critical() -> None:
    # Nothing completed in the 90-day history, so there's no p85 line; work in
    # progress longer than the whole history is aging by any measure.
    done_long_ago = [
        _stream((EventType.CREATED, 125), (EventType.STARTED, 122), (EventType.COMPLETED, 120))
        for _ in range(10)
    ]
    stalled = [_stream((EventType.CREATED, 151), (EventType.STARTED, 150)) for _ in range(6)]

    health = compute_delivery_health([*done_long_ago, *stalled], now=NOW)

    risk = next(c for c in health.components if c.name == "risk")
    assert health.band == "critical"
    assert risk.reason.startswith("6 of 6")
    assert "over 90 days" in risk.reason


@pytest.mark.parametrize("value", [6, 366, 30.5])
def test_aging_history_days_is_a_whole_number_from_7_to_365(value: object) -> None:
    with pytest.raises(ValueError, match="aging_history_days"):
        apply_overrides(DEFAULT_RULES, {"aging_history_days": value})
