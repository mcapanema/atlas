from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import HEALTH_COMPONENTS, MetricRules, resolve_rules
from app.domain.metrics.aging import compute_aging_wip
from app.domain.metrics.health import compute_delivery_health
from app.domain.metrics.history import compute_flow_history
from app.domain.metrics.samples import FlowSample
from app.domain.work_items.entities import WorkItem

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _stream(*steps: tuple[EventType, int]) -> list[Event]:
    item_id = uuid4()
    return [
        Event(work_item_id=item_id, type=type_, occurred_at=NOW - timedelta(days=days))
        for type_, days in steps
    ]


# Two completions in the 30-day window (lead 1d and 3d), two items in progress and a backlog item.
SCOPE = [
    _stream((EventType.CREATED, 10), (EventType.STARTED, 10), (EventType.COMPLETED, 9)),
    _stream((EventType.CREATED, 10), (EventType.STARTED, 10), (EventType.COMPLETED, 7)),
    _stream((EventType.CREATED, 4), (EventType.STARTED, 3)),
    _stream((EventType.CREATED, 4), (EventType.STARTED, 3)),
    _stream((EventType.CREATED, 40)),  # backlog: history covers the window
]


def _only(component: str) -> MetricRules:
    """Every health weight 0 except `component`'s; any sample scores (SCOPE is tiny)."""
    weights = {f"weight_{name}": 0.0 for name in HEALTH_COMPONENTS if name != component}
    return resolve_rules({"health_min_sample": 1, **weights})


def test_zero_weights_drop_components_from_the_score() -> None:
    health = compute_delivery_health(SCOPE, now=NOW, rules=_only("predictability"))

    assert [c.name for c in health.components] == ["predictability"]
    assert health.score == health.components[0].score


def test_predictability_scale_follows_the_worst_ratio() -> None:
    # lead times 1d and 3d: p50 2d, p95 2.9d -> ratio 1.45, on a log scale:
    # 100 * (1 - ln 1.45 / ln worst)
    rules = _only("predictability")

    default = compute_delivery_health(SCOPE, now=NOW, rules=rules)
    tighter = compute_delivery_health(
        SCOPE, now=NOW, rules=replace(rules, predictability_worst_ratio=2.0)
    )

    assert (default.score, tighter.score) == (88, 46)


def test_predictability_halves_at_the_square_root_of_the_worst_ratio() -> None:
    # Log scale: every doubling of the spread costs the same points, so a
    # spread of sqrt(worst) scores exactly half.
    rules = replace(_only("predictability"), predictability_worst_ratio=1.45**2)

    assert compute_delivery_health(SCOPE, now=NOW, rules=rules).score == 50


def test_stability_scale_follows_the_best_and_worst_weeks() -> None:
    # WIP 2 against 2 completions in 30 days: 4.29 weeks of throughput
    rules = _only("stability")

    default = compute_delivery_health(SCOPE, now=NOW, rules=rules)
    wider = compute_delivery_health(
        SCOPE,
        now=NOW,
        rules=replace(rules, stability_best_weeks=0.0, stability_worst_weeks=10.0),
    )

    assert (default.score, wider.score) == (18, 57)


def test_band_cutoffs_follow_the_rules() -> None:
    rules = _only("stability")  # scores 18

    def band(**cutoffs: Any) -> str | None:
        return compute_delivery_health(SCOPE, now=NOW, rules=replace(rules, **cutoffs)).band

    assert band() == "critical"
    assert band(healthy_min=50, warning_min=15) == "warning"
    assert band(healthy_min=18, warning_min=10) == "healthy"


def test_health_risk_uses_the_aging_percentile() -> None:
    health = compute_delivery_health(
        SCOPE, now=NOW, rules=replace(_only("risk"), aging_percentile=50)
    )

    assert "p50" in health.components[0].reason


def _pair(
    title: str, *, started_days: int, completed_days: int | None = None
) -> tuple[WorkItem, FlowSample]:
    item = WorkItem(team_id=uuid4(), title=title, state="in_progress")
    sample = FlowSample(
        created_at=NOW - timedelta(days=30),
        started_at=NOW - timedelta(days=started_days),
        completed_at=NOW - timedelta(days=completed_days) if completed_days is not None else None,
        blocked_time=timedelta(0),
    )
    return item, sample


def test_aging_flag_and_reference_follow_the_aging_percentile() -> None:
    pairs = [
        _pair("Fast", started_days=10, completed_days=8),  # cycle 2d
        _pair("Slow", started_days=12, completed_days=4),  # cycle 8d
        _pair("Open", started_days=6),
    ]

    at_p85 = compute_aging_wip(pairs, now=NOW)
    at_p50 = compute_aging_wip(pairs, now=NOW, aging_percentile=50)

    assert at_p85.percentile == 85
    assert not at_p85.items[0].over_percentile  # 6d < p85 7.1d
    assert at_p50.percentile == 50
    assert at_p50.items[0].over_percentile  # 6d > p50 5d
    assert at_p50.cycle_time_percentile == timedelta(days=5)


def test_daily_bucket_cut_over_follows_the_rule() -> None:
    daily = compute_flow_history([], now=NOW, window_days=14)
    weekly = compute_flow_history(
        [], now=NOW, window_days=14, rules=MetricRules(daily_bucket_max_days=7)
    )

    assert daily.bucket_days == 1
    assert (weekly.bucket_days, len(weekly.buckets)) == (7, 2)


def test_history_counts_throughput_from_the_samples_it_is_given() -> None:
    stream = _stream((EventType.CREATED, 5), (EventType.STARTED, 4), (EventType.COMPLETED, 2))
    undelivered = FlowSample(
        created_at=NOW - timedelta(days=5),
        started_at=NOW - timedelta(days=4),
        completed_at=None,
        blocked_time=timedelta(0),
    )

    history = compute_flow_history([stream], now=NOW, window_days=14, samples=[undelivered])

    assert sum(b.completed for b in history.buckets) == 0
