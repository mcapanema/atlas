from datetime import UTC
from uuid import UUID, uuid4

import pytest

from app.domain.work_items.entities import DEFAULT_STATE, WorkItem, WorkItemType


def test_work_item_defaults() -> None:
    item = WorkItem(team_id=uuid4(), title="Add login")

    assert isinstance(item.id, UUID)
    assert item.created_at.tzinfo == UTC
    assert item.type is WorkItemType.TASK
    assert item.state == "backlog"
    assert item.project_id is None


def test_work_item_strips_title() -> None:
    item = WorkItem(team_id=uuid4(), title="  Add login  ")

    assert item.title == "Add login"


def test_work_item_rejects_empty_title() -> None:
    with pytest.raises(ValueError, match="WorkItem title must not be empty"):
        WorkItem(team_id=uuid4(), title="   ")


def test_work_item_type_is_string_valued() -> None:
    assert WorkItemType.BUG == "bug"  # type: ignore[comparison-overlap]
    assert WorkItemType("spike") is WorkItemType.SPIKE


def test_new_work_item_defaults_to_the_default_state() -> None:
    item = WorkItem(team_id=uuid4(), title="Ship it")
    assert item.state == DEFAULT_STATE == "backlog"
