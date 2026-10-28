from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.domain.events.entities import EventType
from app.domain.sync.source import SourceEvent, SourcePerson, SourceWorkItem
from app.domain.work_items.entities import WorkItemType


def test_source_event_requires_timezone_aware_occurred_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SourceEvent(
            external_id="h1",
            type=EventType.STARTED,
            occurred_at=datetime(2026, 7, 1),  # noqa: DTZ001 — naive on purpose
        )


def test_source_work_item_assignee_is_a_source_person() -> None:
    item = SourceWorkItem(
        external_id="i1",
        title="Fix",
        type=WorkItemType.TASK,
        state="Todo",
        team_external_id="t1",
        project_external_id=None,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        assignee=SourcePerson("u1", "Ada"),
    )

    assert item.assignee is not None
    assert item.assignee.external_id == "u1"


def test_source_work_item_holds_immutable_events() -> None:
    event = SourceEvent(
        external_id="h1",
        type=EventType.CREATED,
        occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    item = SourceWorkItem(
        external_id="i1",
        title="Fix login",
        type=WorkItemType.TASK,
        state="Backlog",
        team_external_id="t1",
        project_external_id=None,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        events=(event,),
    )

    assert item.events == (event,)
    with pytest.raises(AttributeError):
        item.title = "changed"  # type: ignore[misc]


def test_source_person_email_defaults_to_none_and_is_frozen() -> None:
    person = SourcePerson("u1", "Ada")

    assert person.email is None
    with pytest.raises(FrozenInstanceError):
        person.name = "Grace"  # type: ignore[misc]
