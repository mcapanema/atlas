from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.events.timeline import BlockedPeriod, blocked_periods
from app.domain.metric_rules.entities import MetricRules
from app.domain.metrics.health import DeliveryHealth, compute_delivery_health
from app.domain.metrics.samples import derive_flow_sample

ITEM = uuid4()
RELATIONS = MetricRules(blocked_by_relations=True)


def _day(day: int) -> datetime:
    return datetime(2026, 9, day, tzinfo=UTC)


def _on(type_: EventType, day: int, detail: str | None = None) -> Event:
    return Event(work_item_id=ITEM, type=type_, occurred_at=_day(day), detail=detail)


def test_explicit_events_pair_as_before() -> None:
    events = [
        _on(EventType.BLOCKED, 1),
        _on(EventType.BLOCKED, 2),  # already blocked: ignored
        _on(EventType.UNBLOCKED, 3),
        _on(EventType.UNBLOCKED, 4),  # nothing open: ignored
    ]

    assert blocked_periods(events) == (BlockedPeriod(_day(1), _day(3)),)


def test_label_events_block_only_when_the_rules_call_the_label_blocked() -> None:
    events = [
        _on(EventType.LABEL_ADDED, 1, "Blocked"),
        _on(EventType.LABEL_ADDED, 2, "regras-blockly"),
        _on(EventType.LABEL_REMOVED, 5, "Blocked"),
    ]

    assert blocked_periods(events) == (BlockedPeriod(_day(1), _day(5)),)
    assert blocked_periods(events, MetricRules(blocked_label_pattern=False)) == ()


def test_blocker_events_count_only_with_the_relations_rule() -> None:
    events = [_on(EventType.BLOCKER_ADDED, 1, "DEP-1"), _on(EventType.BLOCKER_CLEARED, 4, "DEP-1")]

    assert blocked_periods(events) == ()
    assert blocked_periods(events, RELATIONS) == (BlockedPeriod(_day(1), _day(4)),)


def test_overlapping_sources_form_one_period() -> None:
    events = [
        _on(EventType.BLOCKER_ADDED, 1, "DEP-1"),
        _on(EventType.LABEL_ADDED, 2, "Blocked"),
        _on(EventType.BLOCKER_ADDED, 3, "DEP-2"),
        _on(EventType.BLOCKER_CLEARED, 5, "DEP-1"),
        _on(EventType.LABEL_REMOVED, 6, "Blocked"),
        _on(EventType.BLOCKER_CLEARED, 7, "DEP-2"),
        _on(EventType.BLOCKER_ADDED, 9, "DEP-1"),  # blocker reopened
    ]

    assert blocked_periods(events, RELATIONS) == (
        BlockedPeriod(_day(1), _day(7)),
        BlockedPeriod(_day(9), None),
    )


def test_a_clear_for_a_blocker_never_opened_is_ignored() -> None:
    # Truncated history: the "ab" fell off the 250-entry page.
    events = [_on(EventType.BLOCKER_CLEARED, 2, "DEP-1"), _on(EventType.BLOCKER_ADDED, 3, "DEP-2")]

    assert blocked_periods(events, RELATIONS) == (BlockedPeriod(_day(3), None),)


def test_flow_sample_counts_relation_blocked_time_and_blocked_now() -> None:
    events = [
        _on(EventType.CREATED, 1),
        _on(EventType.STARTED, 2),
        _on(EventType.BLOCKER_ADDED, 3, "DEP-1"),
        _on(EventType.BLOCKER_CLEARED, 5, "DEP-1"),
        _on(EventType.BLOCKER_ADDED, 6, "DEP-2"),
    ]

    default = derive_flow_sample(events)
    relations = derive_flow_sample(events, RELATIONS)
    finished = derive_flow_sample([*events, _on(EventType.COMPLETED, 8)], RELATIONS)

    assert default is not None
    assert relations is not None
    assert finished is not None
    assert (default.blocked_time, default.blocked_now) == (timedelta(0), False)
    assert relations.blocked_now is True
    assert finished.blocked_time == timedelta(days=4)  # 3→5, then 6→8 (clipped)


def test_health_risk_reads_blocked_now_from_the_rules() -> None:
    now = _day(10)
    stream = [
        _on(EventType.CREATED, 1),
        _on(EventType.STARTED, 2),
        _on(EventType.BLOCKER_ADDED, 3, "DEP-1"),
    ]

    default = compute_delivery_health([stream], now=now)
    relations = compute_delivery_health(
        [stream], now=now, samples=[derive_flow_sample(stream, RELATIONS)]
    )

    def risk(health: DeliveryHealth) -> str:
        return next(c.reason for c in health.components if c.name == "risk")

    assert risk(default).startswith("0 of 1")
    assert risk(relations).startswith("1 of 1")
