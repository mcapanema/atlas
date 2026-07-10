# app/infrastructure/connectors/linear/mapping.py
"""Translate Linear GraphQL payloads into platform-neutral Source* types.

Linear specifics (field names, workflow-state `type` values) stop here —
nothing outside this package sees a Linear payload.
"""

from datetime import datetime
from typing import Any

from app.domain.events.entities import EventType
from app.domain.sync.source import SourceEvent, SourceProject, SourceTeam, SourceWorkItem
from app.domain.work_items.entities import WorkItemType


def map_team(node: dict[str, Any]) -> SourceTeam:
    return SourceTeam(external_id=node["id"], name=node["name"])


def map_project(node: dict[str, Any]) -> SourceProject:
    # ponytail: Linear projects can span multiple teams; we keep only the
    # first. Model a many-to-many if cross-team projects ever matter.
    team_nodes = node["teams"]["nodes"]
    return SourceProject(
        external_id=node["id"],
        name=node["name"],
        team_external_id=team_nodes[0]["id"] if team_nodes else None,
    )


def map_issue(node: dict[str, Any]) -> SourceWorkItem:
    created_at = datetime.fromisoformat(node["createdAt"])
    events = [
        # Linear's history doesn't include creation — synthesize it, with a
        # deterministic external_id so re-syncs stay idempotent.
        SourceEvent(
            external_id=f"{node['id']}:created",
            type=EventType.CREATED,
            occurred_at=created_at,
        )
    ]
    for entry in node["history"]["nodes"]:
        event = map_history_entry(entry)
        if event is not None:
            events.append(event)
    project = node.get("project")
    return SourceWorkItem(
        external_id=node["id"],
        title=node["title"],
        # ponytail: Linear has no built-in story/task/bug field — everything
        # maps to TASK. Classify from labels if type metrics are ever needed.
        type=WorkItemType.TASK,
        state=node["state"]["name"],
        team_external_id=node["team"]["id"],
        project_external_id=project["id"] if project else None,
        created_at=created_at,
        events=tuple(events),
    )


def map_history_entry(entry: dict[str, Any]) -> SourceEvent | None:
    """One issue-history entry → SourceEvent; None for non-state changes.

    ponytail: assignment/label/priority history is skipped — only state
    transitions feed flow metrics today. Map toAssignee → EventType.ASSIGNED
    here when assignment analytics are needed.
    """
    to_state = entry.get("toState")
    if to_state is None:
        return None
    from_state = entry.get("fromState")
    return SourceEvent(
        external_id=entry["id"],
        type=_event_type(from_state, to_state),
        occurred_at=datetime.fromisoformat(entry["createdAt"]),
        from_state=from_state["name"] if from_state else None,
        to_state=to_state["name"],
    )


def _event_type(from_state: dict[str, Any] | None, to_state: dict[str, Any]) -> EventType:
    from_type = from_state["type"] if from_state else None
    to_type = to_state["type"]
    if to_type == "started" and from_type != "started":
        return EventType.STARTED
    if to_type == "completed" and from_type != "completed":
        return EventType.COMPLETED
    return EventType.STATE_CHANGED
