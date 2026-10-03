# tests/infrastructure/test_linear_mapping.py
import logging
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.events.entities import EventType
from app.infrastructure.connectors.linear.mapping import (
    HISTORY_PAGE_SIZE,
    blocked_label_ids,
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
    [event] = map_history_entry(_entry("backlog", "started", "Backlog", "In Progress"))

    assert event.type is EventType.STARTED
    assert event.from_state == "Backlog"
    assert event.to_state == "In Progress"
    assert event.occurred_at == datetime(2026, 7, 2, 9, 0, tzinfo=UTC)


def test_history_entry_within_started_is_state_changed() -> None:
    [event] = map_history_entry(_entry("started", "started", "In Progress", "In Review"))

    assert event.type is EventType.STATE_CHANGED


def test_history_entry_entering_completed_is_completed() -> None:
    [event] = map_history_entry(_entry("started", "completed"))

    assert event.type is EventType.COMPLETED


def test_history_entry_without_to_state_is_skipped() -> None:
    entry = {
        "id": "h2",
        "createdAt": "2026-07-02T10:00:00.000Z",
        "fromState": None,
        "toState": None,
    }

    assert map_history_entry(entry) == []


BLOCKED_IDS = frozenset({"lbl-blocked"})


def _label_entry(added: list[str], removed: list[str]) -> dict[str, Any]:
    return {
        "id": "h9",
        "createdAt": "2026-07-02T11:00:00.000Z",
        "fromState": None,
        "toState": None,
        "addedLabelIds": added,
        "removedLabelIds": removed,
    }


def test_blocked_label_added_emits_blocked() -> None:
    [event] = map_history_entry(_label_entry(["lbl-blocked"], []), BLOCKED_IDS)

    assert event.type is EventType.BLOCKED
    assert event.external_id == "h9:blocked"
    assert event.from_state is None
    assert event.to_state is None
    assert event.occurred_at == datetime(2026, 7, 2, 11, 0, tzinfo=UTC)


def test_blocked_label_removed_emits_unblocked() -> None:
    [event] = map_history_entry(_label_entry([], ["lbl-blocked"]), BLOCKED_IDS)

    assert event.type is EventType.UNBLOCKED
    assert event.external_id == "h9:unblocked"


def test_non_blocked_label_changes_emit_nothing() -> None:
    assert map_history_entry(_label_entry(["lbl-bug"], ["lbl-chore"]), BLOCKED_IDS) == []


def test_label_changes_without_blocked_ids_emit_nothing() -> None:
    assert map_history_entry(_label_entry(["lbl-blocked"], [])) == []


def test_state_change_and_blocked_label_in_one_entry_emits_both() -> None:
    entry = {
        **_entry("backlog", "started", "Backlog", "In Progress"),
        "addedLabelIds": ["lbl-blocked"],
    }

    events = map_history_entry(entry, BLOCKED_IDS)

    assert [e.type for e in events] == [EventType.STARTED, EventType.BLOCKED]
    assert events[0].external_id == "h1"
    assert events[1].external_id == "h1:blocked"


def test_blocked_label_ids_matches_block_substring_case_insensitively() -> None:
    ids = blocked_label_ids(
        [
            {"id": "l1", "name": "Blocked"},
            {"id": "l2", "name": "blocker: external"},
            {"id": "l3", "name": "bug"},
        ]
    )

    assert ids == {"l1", "l2"}


def test_map_issue_threads_blocked_ids_through_history() -> None:
    node = {
        **ISSUE_NODE,
        "history": {
            "nodes": [
                *ISSUE_NODE["history"]["nodes"],
                _label_entry(["lbl-blocked"], []),
            ]
        },
    }

    item = map_issue(node, BLOCKED_IDS)

    assert [e.type for e in item.events] == [
        EventType.CREATED,
        EventType.STARTED,
        EventType.BLOCKED,
    ]


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


def test_map_issue_parses_completed_at() -> None:
    node = {**ISSUE_NODE, "completedAt": "2026-07-03T09:00:00.000Z"}

    assert map_issue(node).completed_at == datetime(2026, 7, 3, 9, 0, tzinfo=UTC)


def test_map_issue_without_completed_at_is_open() -> None:
    assert map_issue(ISSUE_NODE).completed_at is None  # key absent entirely
    assert map_issue({**ISSUE_NODE, "completedAt": None}).completed_at is None


def test_map_issue_at_history_cap_logs_truncation_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    entries = [{**_entry("backlog", "started"), "id": f"h{i}"} for i in range(HISTORY_PAGE_SIZE)]
    node = {**ISSUE_NODE, "history": {"nodes": entries}}

    with caplog.at_level(logging.WARNING, logger="app.infrastructure.connectors.linear.mapping"):
        map_issue(node)

    assert any("history hit" in r.getMessage() and "i1" in r.getMessage() for r in caplog.records)


def test_map_issue_below_history_cap_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.infrastructure.connectors.linear.mapping"):
        map_issue(ISSUE_NODE)

    assert not caplog.records


def test_history_entry_leaving_started_for_backlog_also_emits_stopped() -> None:
    events = map_history_entry(_entry("started", "backlog", "In Progress", "Backlog"))

    assert [e.type for e in events] == [EventType.STATE_CHANGED, EventType.STOPPED]
    assert events[1].external_id == "h1:stopped"
    assert events[1].occurred_at == datetime(2026, 7, 2, 9, 0, tzinfo=UTC)


def test_history_entry_leaving_started_for_canceled_also_emits_stopped() -> None:
    events = map_history_entry(_entry("started", "canceled", "In Progress", "Canceled"))

    assert [e.type for e in events] == [EventType.STATE_CHANGED, EventType.STOPPED]


def test_history_entry_leaving_unstarted_for_canceled_emits_no_stopped() -> None:
    [event] = map_history_entry(_entry("unstarted", "canceled", "Todo", "Canceled"))

    assert event.type is EventType.STATE_CHANGED


def test_map_issue_created_in_a_started_state_starts_at_creation() -> None:
    # Linear returns history newest-first: the earliest transition is listed last.
    node = {
        **ISSUE_NODE,
        "history": {
            "nodes": [
                {
                    "id": "h3",
                    "createdAt": "2026-07-04T09:00:00.000Z",
                    "fromState": {"name": "In Review", "type": "started"},
                    "toState": {"name": "Done", "type": "completed"},
                },
                {
                    "id": "h2",
                    "createdAt": "2026-07-02T09:00:00.000Z",
                    "fromState": {"name": "In Progress", "type": "started"},
                    "toState": {"name": "In Review", "type": "started"},
                },
            ]
        },
    }

    item = map_issue(node)

    started = [e for e in item.events if e.type is EventType.STARTED]
    assert [e.external_id for e in started] == ["i1:started"]
    assert started[0].occurred_at == item.created_at


def test_map_issue_earliest_transition_decides_the_initial_state() -> None:
    # Newest entry leaves a started state, but the earliest leaves Backlog:
    # the item was created in Backlog, so no synthetic start.
    node = {
        **ISSUE_NODE,
        "history": {
            "nodes": [
                {
                    "id": "h3",
                    "createdAt": "2026-07-04T09:00:00.000Z",
                    "fromState": {"name": "In Progress", "type": "started"},
                    "toState": {"name": "Done", "type": "completed"},
                },
                *ISSUE_NODE["history"]["nodes"],
            ]
        },
    }

    item = map_issue(node)

    assert [e.external_id for e in item.events if e.type is EventType.STARTED] == ["h1"]


def test_map_issue_created_in_started_without_transitions_uses_current_state() -> None:
    item = map_issue({**ISSUE_NODE, "history": {"nodes": []}})

    assert [e.type for e in item.events] == [EventType.CREATED, EventType.STARTED]
    assert item.events[1].external_id == "i1:started"
    assert item.events[1].occurred_at == item.created_at


def test_map_issue_created_in_backlog_without_transitions_gets_no_start() -> None:
    node = {
        **ISSUE_NODE,
        "state": {"name": "Backlog", "type": "backlog"},
        "history": {"nodes": []},
    }

    assert [e.type for e in map_issue(node).events] == [EventType.CREATED]


def test_map_issue_canceled_at_emits_canceled_keyed_by_time() -> None:
    first = map_issue({**ISSUE_NODE, "canceledAt": "2026-07-05T09:00:00.000Z"})
    again = map_issue({**ISSUE_NODE, "canceledAt": "2026-07-09T09:00:00.000Z"})

    [canceled] = [e for e in first.events if e.type is EventType.CANCELED]
    assert canceled.occurred_at == datetime(2026, 7, 5, 9, 0, tzinfo=UTC)
    assert canceled.external_id == "i1:canceled:2026-07-05T09:00:00.000Z"
    # Re-canceled after a reopen: a new canceledAt must yield a new event.
    assert [e.external_id for e in again.events if e.type is EventType.CANCELED] == [
        "i1:canceled:2026-07-09T09:00:00.000Z"
    ]


def test_map_issue_without_canceled_at_emits_no_canceled() -> None:
    for node in (ISSUE_NODE, {**ISSUE_NODE, "canceledAt": None}):
        assert not [e for e in map_issue(node).events if e.type is EventType.CANCELED]


def test_map_issue_created_in_a_completed_state_completes_at_creation() -> None:
    node = {
        **ISSUE_NODE,
        "state": {"name": "Done", "type": "completed"},
        "completedAt": "2026-07-01T10:00:00.120Z",
        "history": {"nodes": []},
    }

    item = map_issue(node)

    assert [e.type for e in item.events] == [EventType.CREATED, EventType.COMPLETED]
    assert item.events[1].external_id == "i1:created-done"
    assert item.events[1].occurred_at == item.created_at


def test_map_issue_created_done_then_moved_within_done_still_completes_at_creation() -> None:
    node = {
        **ISSUE_NODE,
        "state": {"name": "Released", "type": "completed"},
        "history": {
            "nodes": [
                {
                    "id": "h5",
                    "createdAt": "2026-07-03T09:00:00.000Z",
                    "fromState": {"name": "Done", "type": "completed"},
                    "toState": {"name": "Released", "type": "completed"},
                }
            ]
        },
    }

    item = map_issue(node)

    completed = [e for e in item.events if e.type is EventType.COMPLETED]
    assert [e.external_id for e in completed] == ["i1:created-done"]


def test_map_issue_created_in_todo_and_completed_later_gets_no_created_done() -> None:
    node = {
        **ISSUE_NODE,
        "state": {"name": "Done", "type": "completed"},
        "history": {
            "nodes": [
                {
                    "id": "h6",
                    "createdAt": "2026-07-01T10:00:30.000Z",
                    "fromState": {"name": "Todo", "type": "unstarted"},
                    "toState": {"name": "Done", "type": "completed"},
                }
            ]
        },
    }

    completed = [e for e in map_issue(node).events if e.type is EventType.COMPLETED]

    assert [e.external_id for e in completed] == ["h6"]
