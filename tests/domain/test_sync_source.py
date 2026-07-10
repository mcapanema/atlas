from datetime import UTC, datetime

import pytest

from app.domain.events.entities import EventType
from app.domain.sync.source import SourceEvent, SourceWorkItem
from app.domain.work_items.entities import WorkItemType


def test_source_event_requires_timezone_aware_occurred_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SourceEvent(
            external_id="h1",
            type=EventType.STARTED,
            occurred_at=datetime(2026, 7, 1),  # naive on purpose
        )


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
