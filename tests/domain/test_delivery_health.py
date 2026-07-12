from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.metrics.health import compute_delivery_health

NOW = datetime(2026, 7, 10, tzinfo=UTC)


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


def test_healthy_scope_scores_high_with_all_five_components() -> None:
    streams = [
        _stream((EventType.CREATED, 20), (EventType.STARTED, 19), (EventType.COMPLETED, 17)),
        _stream((EventType.CREATED, 10), (EventType.STARTED, 9), (EventType.COMPLETED, 7)),
        _stream((EventType.CREATED, 6), (EventType.STARTED, 5), (EventType.COMPLETED, 3)),
        _stream((EventType.CREATED, 4), (EventType.STARTED, 2)),  # fresh WIP
    ]

    health = compute_delivery_health(streams, now=NOW)

    assert health.band == "healthy"
    assert health.score is not None and health.score >= 70
    assert {c.name for c in health.components} == {
        "predictability",
        "efficiency",
        "flow",
        "stability",
        "risk",
    }


def test_open_blocked_wip_drags_risk_to_zero() -> None:
    streams = [
        _stream((EventType.CREATED, 20), (EventType.STARTED, 19), (EventType.COMPLETED, 17)),
        _stream((EventType.CREATED, 15), (EventType.STARTED, 14), (EventType.BLOCKED, 13)),
    ]

    health = compute_delivery_health(streams, now=NOW)

    risk = next(c for c in health.components if c.name == "risk")
    assert risk.score == 0
    assert "1 of 1" in risk.reason


def test_components_without_data_are_omitted() -> None:
    streams = [_stream((EventType.CREATED, 5), (EventType.STARTED, 4))]

    health = compute_delivery_health(streams, now=NOW)

    names = {c.name for c in health.components}
    assert "predictability" not in names  # nothing completed in window
    assert "stability" not in names
    assert "risk" in names  # one unblocked, un-aged in-progress item -> score 100
