from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules, resolve_rules
from app.domain.metrics.health import compute_delivery_health
from app.domain.metrics.samples import derive_flow_sample
from tests.fakes import CALENDAR_DAYS

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _stream(*steps: tuple[EventType, int]) -> list[Event]:
    item_id = uuid4()
    return [
        Event(work_item_id=item_id, type=type_, occurred_at=NOW - timedelta(days=days))
        for type_, days in steps
    ]


# Completed long before the 30-day window: no window component sees it, but
# its 1-day cycle sets the aging line every stuck item is past.
OLD_DONE = _stream((EventType.CREATED, 70), (EventType.STARTED, 69), (EventType.COMPLETED, 68))


BACKLOG = _stream((EventType.CREATED, 40))  # open backlog: no component counts it


def _stuck(count: int) -> list[list[Event]]:
    return [_stream((EventType.CREATED, 40), (EventType.STARTED, 30)) for _ in range(count)]


def _done(*completed_days_ago: int) -> list[list[Event]]:
    return [
        _stream((EventType.CREATED, 12), (EventType.STARTED, 10), (EventType.COMPLETED, days))
        for days in completed_days_ago
    ]


def _prior(count: int) -> list[list[Event]]:
    """`count` 2-day cycles completed 40 days ago: a service level for predictability."""
    return [
        _stream((EventType.CREATED, 60), (EventType.STARTED, 42), (EventType.COMPLETED, 40))
        for _ in range(count)
    ]


def test_the_floor_defaults_to_five_items() -> None:
    assert DEFAULT_RULES.health_min_sample == 5


def test_one_stuck_item_no_longer_scores_the_team() -> None:
    # The live Support / SRE & Data / AI Services case: 0, critical from 1 of 1.
    health = compute_delivery_health([OLD_DONE, *_stuck(1)], now=NOW)

    assert (health.score, health.band, health.components) == (None, None, ())


def test_a_floor_of_one_scores_the_same_item() -> None:
    rules = MetricRules(health_min_sample=1)

    health = compute_delivery_health([OLD_DONE, *_stuck(1)], now=NOW, rules=rules)

    assert (health.score, health.band) == (0, "critical")


def test_a_stalled_team_with_enough_stuck_work_still_reads_critical() -> None:
    # Review focus 5: the floor hides anecdotes, not a stalled team.
    health = compute_delivery_health([OLD_DONE, *_stuck(5)], now=NOW)

    assert [c.name for c in health.components] == ["risk"]
    assert health.components[0].reason.startswith("5 of 5")
    assert (health.score, health.band) == (0, "critical")


def test_four_completions_are_not_enough_for_the_completion_components() -> None:
    health = compute_delivery_health(_done(9, 8, 6, 3), now=NOW)

    assert health.components == ()


def test_five_completions_score_the_completion_components() -> None:
    health = compute_delivery_health([BACKLOG, *_prior(5), *_done(9, 8, 6, 5, 3)], now=NOW)

    assert {c.name for c in health.components} == {
        "predictability",
        "flow",
        "stability",
    }


def test_four_prior_completions_set_no_service_level() -> None:
    # Review focus 1: the floor applies to the reference too: four prior
    # cycles are an anecdote, not a commitment.
    health = compute_delivery_health([BACKLOG, *_prior(4), *_done(9, 8, 6, 5, 3)], now=NOW)

    assert "predictability" not in {c.name for c in health.components}


def test_a_zero_length_cycle_does_not_count_toward_the_efficiency_floor() -> None:
    # Started and completed in one instant (an automation): flow efficiency
    # can't measure it, so it can't help efficiency reach the floor.
    instant = _stream((EventType.CREATED, 12), (EventType.STARTED, 5), (EventType.COMPLETED, 5))

    health = compute_delivery_health(
        [*_prior(5), *_done(9, 8, 6, 3), instant], now=NOW, rules=MetricRules(weight_efficiency=1.0)
    )

    names = {c.name for c in health.components}
    assert "efficiency" not in names
    assert "predictability" in names  # still 5 completions in the window


@pytest.mark.parametrize("value", [0, 51, 2.5])
def test_health_min_sample_is_a_whole_number_from_1_to_50(value: object) -> None:
    with pytest.raises(ValueError, match="health_min_sample"):
        resolve_rules({"health_min_sample": value})


def _risk_reason(rules: MetricRules) -> str:
    """Health for one item started Fri 12:00 and open at Mon 12:00, past a 2-day cycle line."""
    now = datetime(2026, 10, 19, 12, tzinfo=UTC)  # Monday
    item = uuid4()

    def event(type_: EventType, at: datetime) -> Event:
        return Event(work_item_id=item, type=type_, occurred_at=at)

    done = uuid4()
    reference = [  # a 2-day cycle on weekdays sets the aging line
        Event(
            work_item_id=done, type=EventType.CREATED, occurred_at=datetime(2026, 9, 1, tzinfo=UTC)
        ),
        Event(
            work_item_id=done, type=EventType.STARTED, occurred_at=datetime(2026, 9, 1, tzinfo=UTC)
        ),
        Event(
            work_item_id=done,
            type=EventType.COMPLETED,
            occurred_at=datetime(2026, 9, 3, tzinfo=UTC),
        ),
    ]
    open_item = [
        event(EventType.CREATED, datetime(2026, 10, 16, 9, tzinfo=UTC)),
        event(EventType.STARTED, datetime(2026, 10, 16, 12, tzinfo=UTC)),  # Friday
    ]
    rules = replace(rules, health_min_sample=1)
    streams = [reference, open_item]
    health = compute_delivery_health(
        streams, now=now, rules=rules, samples=[derive_flow_sample(s, rules) for s in streams]
    )
    return next(c.reason for c in health.components if c.name == "risk")


def test_risk_ages_in_progress_items_on_working_days() -> None:
    # Fri 12:00 -> Mon 12:00 is 1 working day: inside the 2-day line.
    assert _risk_reason(DEFAULT_RULES).startswith("0 of 1")


def test_risk_on_a_seven_day_calendar_counts_the_weekend() -> None:
    # The same item is 3 calendar days old: past the 2-day line.
    assert _risk_reason(CALENDAR_DAYS).startswith("1 of 1")
