from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.events.entities import Event, EventType


def test_event_defaults() -> None:
    event = Event(
        work_item_id=uuid4(),
        type=EventType.STARTED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert isinstance(event.id, UUID)
    assert event.recorded_at.tzinfo == UTC
    assert event.from_state is None and event.to_state is None


def test_event_is_immutable() -> None:
    event = Event(
        work_item_id=uuid4(),
        type=EventType.STARTED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(FrozenInstanceError):
        event.to_state = "done"  # type: ignore[misc]


def test_event_rejects_naive_occurred_at() -> None:
    with pytest.raises(ValueError, match="Event.occurred_at must be timezone-aware"):
        Event(
            work_item_id=uuid4(),
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1),  # noqa: DTZ001 — intentionally naive
        )


def test_event_carries_state_transition() -> None:
    event = Event(
        work_item_id=uuid4(),
        type=EventType.STATE_CHANGED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        from_state="backlog",
        to_state="in_progress",
        external_id="lin_hist_1",
    )

    assert event.from_state == "backlog"
    assert event.to_state == "in_progress"
    assert event.external_id == "lin_hist_1"
