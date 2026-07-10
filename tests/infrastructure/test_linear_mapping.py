# tests/infrastructure/test_linear_mapping.py
from datetime import UTC, datetime
from typing import Any

from app.domain.events.entities import EventType
from app.infrastructure.connectors.linear.mapping import (
    map_history_entry,
    map_issue,
    map_project,
    map_team,
)


def test_map_team() -> None:
    team = map_team({"id": "t1", "name": "Platform"})

    assert team.external_id == "t1"
    assert team.name == "Platform"


def test_map_project_takes_first_team() -> None:
    project = map_project(
        {"id": "p1", "name": "Q3 Launch", "teams": {"nodes": [{"id": "t1"}, {"id": "t2"}]}}
    )

    assert project.external_id == "p1"
    assert project.team_external_id == "t1"


def test_map_project_without_teams_has_no_team() -> None:
    project = map_project({"id": "p1", "name": "Q3 Launch", "teams": {"nodes": []}})

    assert project.team_external_id is None


def _entry(
    from_type: str | None, to_type: str, from_name: str = "From", to_name: str = "To"
) -> dict[str, Any]:
    return {
        "id": "h1",
        "createdAt": "2026-07-02T09:00:00.000Z",
        "fromState": {"name": from_name, "type": from_type} if from_type else None,
        "toState": {"name": to_name, "type": to_type},
    }


def test_history_entry_entering_started_is_started() -> None:
    event = map_history_entry(_entry("backlog", "started", "Backlog", "In Progress"))

    assert event is not None
    assert event.type is EventType.STARTED
    assert event.from_state == "Backlog"
    assert event.to_state == "In Progress"
    assert event.occurred_at == datetime(2026, 7, 2, 9, 0, tzinfo=UTC)


def test_history_entry_within_started_is_state_changed() -> None:
    event = map_history_entry(_entry("started", "started", "In Progress", "In Review"))

    assert event is not None
    assert event.type is EventType.STATE_CHANGED


def test_history_entry_entering_completed_is_completed() -> None:
    event = map_history_entry(_entry("started", "completed"))

    assert event is not None
    assert event.type is EventType.COMPLETED


def test_history_entry_without_to_state_is_skipped() -> None:
    entry = {
        "id": "h2",
        "createdAt": "2026-07-02T10:00:00.000Z",
        "fromState": None,
        "toState": None,
    }

    assert map_history_entry(entry) is None


ISSUE_NODE: dict[str, Any] = {
    "id": "i1",
    "title": "Fix login",
    "createdAt": "2026-07-01T10:00:00.000Z",
    "state": {"name": "In Progress", "type": "started"},
    "team": {"id": "t1"},
    "project": None,
    "history": {
        "nodes": [
            {
                "id": "h1",
                "createdAt": "2026-07-02T09:00:00.000Z",
                "fromState": {"name": "Backlog", "type": "backlog"},
                "toState": {"name": "In Progress", "type": "started"},
            },
            {  # an assignment-only entry — must be skipped
                "id": "h2",
                "createdAt": "2026-07-02T10:00:00.000Z",
                "fromState": None,
                "toState": None,
            },
        ]
    },
}


def test_map_issue_synthesizes_created_event_and_maps_history() -> None:
    item = map_issue(ISSUE_NODE)

    assert item.external_id == "i1"
    assert item.title == "Fix login"
    assert item.state == "In Progress"
    assert item.team_external_id == "t1"
    assert item.project_external_id is None
    assert item.created_at == datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    assert [e.type for e in item.events] == [EventType.CREATED, EventType.STARTED]
    assert item.events[0].external_id == "i1:created"
    assert item.events[0].occurred_at == item.created_at


def test_map_issue_with_project() -> None:
    node = {**ISSUE_NODE, "project": {"id": "p1"}}

    assert map_issue(node).project_external_id == "p1"
