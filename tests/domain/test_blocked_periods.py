from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.events.timeline import BlockedPeriod, blocked_periods
from app.domain.metric_rules.entities import MetricRules, resolve_rules
from app.domain.metrics.health import DeliveryHealth, compute_delivery_health
from app.domain.metrics.samples import derive_flow_sample
from tests.fakes import CALENDAR_DAYS

ITEM = uuid4()
RELATIONS = replace(CALENDAR_DAYS, blocked_by_relations=True)
NO_RELATIONS = replace(CALENDAR_DAYS, blocked_by_relations=False)


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

    pattern = MetricRules(blocked_label_pattern=True)

    assert blocked_periods(events, pattern) == (BlockedPeriod(_day(1), _day(5)),)
    assert blocked_periods(events) == ()


def test_blocker_events_count_only_when_the_relations_rule_is_on() -> None:
    events = [_on(EventType.BLOCKER_ADDED, 1, "DEP-1"), _on(EventType.BLOCKER_CLEARED, 4, "DEP-1")]

    assert blocked_periods(events, RELATIONS) == (BlockedPeriod(_day(1), _day(4)),)
    assert blocked_periods(events) == ()


def test_default_rules_block_only_on_explicit_signals() -> None:
    """The 2026-10-29 false positives: a planned "blocked by" relation and a
    billing-rule label ("Bloqueante") no longer block; the Blocked state does."""
    relation = [_on(EventType.BLOCKER_ADDED, 1, "FNG-905")]
    rule_labels = [
        _on(EventType.LABEL_ADDED, 1, "Bloqueante"),
        _on(EventType.LABEL_ADDED, 1, "Bloqueada"),
    ]
    state = [
        Event(
            work_item_id=ITEM,
            type=EventType.STATE_CHANGED,
            occurred_at=_day(2),
            from_state="In Progress",
            to_state="Blocked",
        )
    ]

    assert blocked_periods(relation, CALENDAR_DAYS) == ()
    assert blocked_periods(rule_labels, CALENDAR_DAYS) == ()
    assert blocked_periods(state, CALENDAR_DAYS) == (BlockedPeriod(_day(2), None),)


def test_listed_label_blocks_with_the_pattern_off() -> None:
    """Faturamento & Glosa's real blocked label (FNG-652): listed, it still
    blocks in any case; an unlisted pattern word ("Bloqueante") does not."""
    events = [
        _on(EventType.LABEL_ADDED, 1, "bloqueada"),
        _on(EventType.LABEL_ADDED, 2, "Bloqueante"),
        _on(EventType.LABEL_REMOVED, 3, "Bloqueada"),
    ]
    rules = replace(CALENDAR_DAYS, blocked_label_names=("Bloqueada",))

    assert blocked_periods(events, rules) == (BlockedPeriod(_day(1), _day(3)),)


def test_overrides_turn_the_old_sources_back_on() -> None:
    rules = resolve_rules({"blocked_by_relations": True, "blocked_label_pattern": True})
    events = [
        _on(EventType.BLOCKER_ADDED, 1, "DEP-1"),
        _on(EventType.LABEL_ADDED, 2, "Bloqueante"),
    ]

    assert blocked_periods(events, rules) == (BlockedPeriod(_day(1), None),)


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

    off = derive_flow_sample(events, NO_RELATIONS)
    relations = derive_flow_sample(events, RELATIONS)
    finished = derive_flow_sample([*events, _on(EventType.COMPLETED, 8)], RELATIONS)

    assert off is not None
    assert relations is not None
    assert finished is not None
    assert (off.blocked_time, off.blocked_now) == (timedelta(0), False)
    assert relations.blocked_now is True
    assert finished.blocked_time == timedelta(days=4)  # 3→5, then 6→8 (clipped)


def test_health_risk_reads_blocked_now_from_the_rules() -> None:
    now = _day(10)
    stream = [
        _on(EventType.CREATED, 1),
        _on(EventType.STARTED, 2),
        _on(EventType.BLOCKER_ADDED, 3, "DEP-1"),
    ]

    any_sample = MetricRules(health_min_sample=1)  # one item: pin the mechanic, not the floor

    off = compute_delivery_health(
        [stream], now=now, samples=[derive_flow_sample(stream, NO_RELATIONS)], rules=any_sample
    )
    relations = compute_delivery_health(
        [stream], now=now, samples=[derive_flow_sample(stream, RELATIONS)], rules=any_sample
    )

    def risk(health: DeliveryHealth) -> str:
        return next(c.reason for c in health.components if c.name == "risk")

    assert risk(off).startswith("0 of 1")
    assert risk(relations).startswith("1 of 1")
