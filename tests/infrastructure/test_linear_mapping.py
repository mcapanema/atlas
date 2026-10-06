# tests/infrastructure/test_linear_mapping.py
import logging
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.events.entities import EventType
from app.domain.work_items.entities import StateType
from app.infrastructure.connectors.linear.mapping import (
    HISTORY_PAGE_SIZE,
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


def _label_entry(added: list[str], removed: list[str]) -> dict[str, Any]:
    return {
        "id": "h9",
        "createdAt": "2026-07-02T11:00:00.000Z",
        "fromState": None,
        "toState": None,
        "addedLabelIds": added,
        "removedLabelIds": removed,
    }


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


def test_map_issue_carries_url() -> None:
    node = {**ISSUE_NODE, "url": "https://linear.app/acme/issue/ENG-1/fix-login"}

    assert map_issue(node).url == "https://linear.app/acme/issue/ENG-1/fix-login"


def test_map_issue_without_url_key_has_none() -> None:
    assert map_issue(ISSUE_NODE).url is None


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


LABELS = {"lbl-blocked": "Blocked", "lbl-bug": "Bug"}


def test_label_changes_map_to_raw_label_events_with_names() -> None:
    events = map_history_entry(_label_entry(["lbl-blocked"], ["lbl-bug"]), LABELS)

    assert [(e.type, e.external_id, e.detail) for e in events] == [
        (EventType.LABEL_ADDED, "h9:label-added:lbl-blocked", "Blocked"),
        (EventType.LABEL_REMOVED, "h9:label-removed:lbl-bug", "Bug"),
    ]
    assert events[0].occurred_at == datetime(2026, 7, 2, 11, 0, tzinfo=UTC)


def test_a_deleted_label_is_skipped() -> None:
    assert map_history_entry(_label_entry(["lbl-gone"], []), LABELS) == []


def test_transition_events_carry_state_types() -> None:
    [event] = map_history_entry(_entry("backlog", "started", "Backlog", "In Progress"))

    assert (event.from_state_type, event.to_state_type) == (StateType.BACKLOG, StateType.STARTED)


def _relation_entry(*changes: tuple[str, str]) -> dict[str, Any]:
    return {
        "id": "h7",
        "createdAt": "2026-10-02T14:51:38.794Z",
        "fromState": None,
        "toState": None,
        "relationChanges": [{"type": code, "identifier": ident} for code, ident in changes],
    }


def test_blocked_side_relation_codes_map_to_blocker_events() -> None:
    events = map_history_entry(
        _relation_entry(("ab", "DEP-1"), ("bo", "DEP-2"), ("rb", "DEP-3"), ("br", "DEP-4"))
    )

    assert [(e.type, e.detail, e.external_id) for e in events] == [
        (EventType.BLOCKER_ADDED, "DEP-1", "h7:blocker:ab:DEP-1"),
        (EventType.BLOCKER_ADDED, "DEP-2", "h7:blocker:bo:DEP-2"),
        (EventType.BLOCKER_CLEARED, "DEP-3", "h7:blocker:rb:DEP-3"),
        (EventType.BLOCKER_CLEARED, "DEP-4", "h7:blocker:br:DEP-4"),
    ]


def test_blocker_side_and_non_blocking_codes_are_ignored(caplog: pytest.LogCaptureFixture) -> None:
    codes = ["ax", "rx", "xr", "xo", "ar", "rr", "ad", "am", "rd", "rm"]

    with caplog.at_level(logging.WARNING):
        events = map_history_entry(_relation_entry(*((code, "X-1") for code in codes)))

    assert events == []
    assert caplog.records == []


def test_an_unknown_blocking_code_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        map_history_entry(_relation_entry(("bz", "X-1")))
        map_history_entry(_relation_entry(("bz", "X-2")))

    assert sum("bz" in r.getMessage() for r in caplog.records) == 1


def test_labels_present_at_creation_are_added_at_creation() -> None:
    node = {
        **ISSUE_NODE,
        "labelIds": ["lbl-blocked", "lbl-bug"],
        "history": {
            "nodes": [
                *ISSUE_NODE["history"]["nodes"],
                # lbl-bug is first mentioned by a removal: it was there from the start
                {**_label_entry([], ["lbl-bug"]), "createdAt": "2026-07-03T00:00:00.000Z"},
            ]
        },
    }

    item = map_issue(node, {**LABELS, "lbl-new": "New"})
    born = [
        e
        for e in item.events
        if e.external_id.endswith(("label-born:lbl-blocked", "label-born:lbl-bug"))
    ]

    assert [(e.type, e.detail, e.occurred_at) for e in born] == [
        (EventType.LABEL_ADDED, "Blocked", datetime(2026, 7, 1, 10, 0, tzinfo=UTC)),
        (EventType.LABEL_ADDED, "Bug", datetime(2026, 7, 1, 10, 0, tzinfo=UTC)),
    ]


def test_map_issue_carries_state_type_labels_and_parent() -> None:
    node = {**ISSUE_NODE, "labelIds": ["lbl-bug", "lbl-gone"], "parent": {"id": "i0"}}

    item = map_issue(node, LABELS)

    assert (item.state_type, item.labels, item.parent_external_id) == (
        StateType.STARTED,
        ("Bug",),
        "i0",
    )


def test_node_without_new_optional_keys_maps_normally() -> None:
    # Review focus 1: a skipped node reads as vanished and sync deletes it.
    node = {
        **ISSUE_NODE,
        "labelIds": None,
        "parent": None,
        "history": {
            "nodes": [
                {**entry, "relationChanges": None} for entry in ISSUE_NODE["history"]["nodes"]
            ]
        },
    }

    item = map_issue(node)

    assert (item.labels, item.parent_external_id) == ((), None)
    assert [e.type for e in item.events] == [EventType.CREATED, EventType.STARTED]


def test_a_null_relation_change_is_skipped_not_fatal() -> None:
    entry = _relation_entry(("ab", "DEP-1"))
    entry["relationChanges"] = [None, {"type": "ab", "identifier": "DEP-1"}]

    events = map_history_entry(entry)

    assert [(e.type, e.detail) for e in events] == [(EventType.BLOCKER_ADDED, "DEP-1")]


def test_long_label_names_and_blockers_are_truncated_to_the_detail_column() -> None:
    long_name = "x" * 300
    entry = {
        **_relation_entry(("ab", long_name)),
        "addedLabelIds": ["l1"],
        "removedLabelIds": [],
    }
    node = {**ISSUE_NODE, "labelIds": ["l1"], "history": {"nodes": [entry]}}

    item = map_issue(node, {"l1": long_name})

    details = [e.detail for e in item.events if e.detail is not None]
    assert details
    assert all(len(d) == 255 for d in details)
    assert item.labels == ("x" * 255,)


def test_a_duplicate_state_is_typed_canceled() -> None:
    node = {**ISSUE_NODE, "state": {"name": "Duplicate", "type": "duplicate"}}

    assert map_issue(node).state_type is StateType.CANCELED


def test_transition_into_duplicate_is_typed_canceled_and_stops() -> None:
    events = map_history_entry(_entry("started", "duplicate", "In Progress", "Duplicate"))

    assert [e.type for e in events] == [EventType.STATE_CHANGED, EventType.STOPPED]
    assert events[0].to_state_type is StateType.CANCELED


def test_an_unknown_state_type_maps_to_none() -> None:
    node = {**ISSUE_NODE, "state": {"name": "Parked", "type": "parked"}}

    assert map_issue(node).state_type is None
