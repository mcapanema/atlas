from datetime import UTC, datetime
from uuid import uuid4

from app.domain.events.entities import Event, EventType
from app.domain.sync.source import SourceEvent, SourceWorkItem
from app.domain.work_items.entities import (
    NOT_STARTED_STATE_TYPES,
    OPEN_STATE_TYPES,
    StateType,
    WorkItem,
    WorkItemType,
)

AT = datetime(2026, 10, 1, tzinfo=UTC)


def test_open_state_types_are_the_four_open_categories_in_workflow_order() -> None:
    assert OPEN_STATE_TYPES == (
        StateType.TRIAGE,
        StateType.BACKLOG,
        StateType.UNSTARTED,
        StateType.STARTED,
    )
    assert set(NOT_STARTED_STATE_TYPES) == {
        StateType.TRIAGE,
        StateType.BACKLOG,
        StateType.UNSTARTED,
    }


def test_work_item_new_facts_default_to_unknown() -> None:
    item = WorkItem(team_id=uuid4(), title="Fix login")

    assert (item.state_type, item.labels, item.parent_id) == (None, (), None)


def test_event_carries_state_types_and_detail() -> None:
    event = Event(
        work_item_id=uuid4(),
        type=EventType.BLOCKER_ADDED,
        occurred_at=AT,
        detail="DEP-1309",
    )
    moved = Event(
        work_item_id=uuid4(),
        type=EventType.STATE_CHANGED,
        occurred_at=AT,
        from_state_type=StateType.COMPLETED,
        to_state_type=StateType.UNSTARTED,
    )

    assert (event.detail, event.from_state_type, event.to_state_type) == ("DEP-1309", None, None)
    assert (moved.from_state_type, moved.to_state_type) == (
        StateType.COMPLETED,
        StateType.UNSTARTED,
    )
    assert EventType.LABEL_ADDED.value == "label_added"
    assert EventType.BLOCKER_CLEARED.value == "blocker_cleared"


def test_source_types_carry_the_new_facts() -> None:
    event = SourceEvent(
        external_id="h1:label-added:l1",
        type=EventType.LABEL_ADDED,
        occurred_at=AT,
        detail="Blocked",
    )
    item = SourceWorkItem(
        external_id="i1",
        title="Fix login",
        type=WorkItemType.TASK,
        state="Todo",
        team_external_id="t1",
        project_external_id=None,
        created_at=AT,
        state_type=StateType.UNSTARTED,
        labels=("Bug",),
        parent_external_id="i0",
    )

    assert event.detail == "Blocked"
    assert (item.state_type, item.labels, item.parent_external_id) == (
        StateType.UNSTARTED,
        ("Bug",),
        "i0",
    )
