"""Translate Linear GraphQL payloads into platform-neutral Source* types.

Linear specifics (field names, workflow-state `type` values) stop here —
nothing outside this package sees a Linear payload.
"""

import logging
from collections.abc import Set as AbstractSet
from datetime import datetime
from typing import Any

from app.domain.events.entities import EventType
from app.domain.sync.source import SourceEvent, SourceProject, SourceTeam, SourceWorkItem
from app.domain.work_items.entities import WorkItemType

logger = logging.getLogger(__name__)

# History page size the issues query requests per issue (the datasource
# interpolates it). A history of exactly this length has likely been
# truncated by the cap — older events are silently missing.
HISTORY_PAGE_SIZE = 250


def blocked_label_ids(label_nodes: list[dict[str, Any]]) -> set[str]:
    """Ids of labels whose name marks blocked work.

    ponytail: case-insensitive 'block' substring, zero config — covers
    "Blocked", "blocked", "blocker: external". Promote to a Settings list
    if a workspace ever needs exact names.
    """
    return {
        node["id"]
        for node in label_nodes
        if "block" in str(node.get("name", "")).lower()
    }


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


def map_issue(node: dict[str, Any], blocked_ids: AbstractSet[str] = frozenset()) -> SourceWorkItem:
    created_at = datetime.fromisoformat(node["createdAt"])
    history_nodes = node["history"]["nodes"]
    if len(history_nodes) >= HISTORY_PAGE_SIZE:
        logger.warning(
            "Linear issue %s history hit the %d-entry page cap; "
            "older events may be missing",
            node["id"],
            HISTORY_PAGE_SIZE,
        )
    events = [
        # Linear's history doesn't include creation — synthesize it, with a
        # deterministic external_id so re-syncs stay idempotent.
        SourceEvent(
            external_id=f"{node['id']}:created",
            type=EventType.CREATED,
            occurred_at=created_at,
        )
    ]
    for entry in history_nodes:
        events.extend(map_history_entry(entry, blocked_ids))
    project = node.get("project")
    # ponytail: only completedAt feeds completed_at — a canceled issue
    # (canceledAt) is neither delivered throughput nor open work; exclude
    # canceled items from scope counts if they ever skew forecasts.
    completed_at = node.get("completedAt")
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
        completed_at=datetime.fromisoformat(completed_at) if completed_at else None,
        events=tuple(events),
    )


def map_history_entry(
    entry: dict[str, Any], blocked_ids: AbstractSet[str] = frozenset()
) -> list[SourceEvent]:
    """One issue-history entry → 0..n SourceEvents.

    State transitions map as before. Blocked-label additions/removals map
    to BLOCKED/UNBLOCKED with derived external_ids — Linear has no native
    blocked event; the workspace's blocked label is the signal.

    ponytail: labels present at issue creation produce no history entry,
    so an item born blocked reads as never blocked. Diff current labels
    against label history if that ever skews blocked time.
    """
    events: list[SourceEvent] = []
    occurred_at = datetime.fromisoformat(entry["createdAt"])
    to_state = entry.get("toState")
    if to_state is not None:
        from_state = entry.get("fromState")
        events.append(
            SourceEvent(
                external_id=entry["id"],
                type=_event_type(from_state, to_state),
                occurred_at=occurred_at,
                from_state=from_state["name"] if from_state else None,
                to_state=to_state["name"],
            )
        )
    if blocked_ids & set(entry.get("addedLabelIds") or ()):
        events.append(
            SourceEvent(
                external_id=f"{entry['id']}:blocked",
                type=EventType.BLOCKED,
                occurred_at=occurred_at,
            )
        )
    if blocked_ids & set(entry.get("removedLabelIds") or ()):
        events.append(
            SourceEvent(
                external_id=f"{entry['id']}:unblocked",
                type=EventType.UNBLOCKED,
                occurred_at=occurred_at,
            )
        )
    return events


def _event_type(from_state: dict[str, Any] | None, to_state: dict[str, Any]) -> EventType:
    from_type = from_state["type"] if from_state else None
    to_type = to_state["type"]
    if to_type == "started" and from_type != "started":
        return EventType.STARTED
    if to_type == "completed" and from_type != "completed":
        return EventType.COMPLETED
    return EventType.STATE_CHANGED
