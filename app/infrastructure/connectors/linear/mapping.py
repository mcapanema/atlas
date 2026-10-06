"""Translate Linear GraphQL payloads into platform-neutral Source* types.

Linear specifics (field names, workflow-state `type` values) stop here —
nothing outside this package sees a Linear payload.
"""

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.domain.events.entities import EventType
from app.domain.sync.source import SourceEvent, SourceProject, SourceTeam, SourceWorkItem
from app.domain.work_items.entities import StateType, WorkItemType

logger = logging.getLogger(__name__)

# History page size the issues query requests per issue (the datasource
# interpolates it). A history of exactly this length has likely been
# truncated by the cap — older events are silently missing.
HISTORY_PAGE_SIZE = 250


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


def _initial_state_type(node: dict[str, Any]) -> str | None:
    """The Linear state type the issue was created in.

    History has no creation entry: the earliest transition's fromState is
    the initial state; with no transitions the issue never left its current
    one. Sorted by createdAt — Linear's history order isn't relied on.
    """
    transitions = [e for e in node["history"]["nodes"] if e.get("toState") is not None]
    if not transitions:
        return str(node["state"]["type"])
    earliest = min(transitions, key=lambda e: datetime.fromisoformat(e["createdAt"]))
    from_state = earliest.get("fromState")
    return str(from_state["type"]) if from_state else None


# Events implied by the state type an issue was created in. Linear's history
# has no creation entry, so these stamp it: born started → STARTED at
# creation; born completed (logged after the fact) → COMPLETED at creation,
# which analytics read as a record, not flow (FlowSample.born_done).
_BORN_IN = {
    "started": ("started", EventType.STARTED),
    "completed": ("created-done", EventType.COMPLETED),
}


def _initial_events(node: dict[str, Any], created_at: datetime) -> list[SourceEvent]:
    """CREATED, plus the STARTED/COMPLETED its initial state implies.

    Deterministic derived external_ids keep re-syncs idempotent and let a
    re-sync backfill items synced before an event kind existed.
    """
    events = [
        SourceEvent(
            external_id=f"{node['id']}:created",
            type=EventType.CREATED,
            occurred_at=created_at,
        )
    ]
    implied = _BORN_IN.get(_initial_state_type(node) or "")
    if implied is not None:
        suffix, event_type = implied
        events.append(
            SourceEvent(
                external_id=f"{node['id']}:{suffix}",
                type=event_type,
                occurred_at=created_at,
            )
        )
    return events


def map_issue(node: dict[str, Any], label_names: Mapping[str, str] | None = None) -> SourceWorkItem:
    names = label_names or {}
    created_at = datetime.fromisoformat(node["createdAt"])
    history_nodes = node["history"]["nodes"]
    if len(history_nodes) >= HISTORY_PAGE_SIZE:
        logger.warning(
            "Linear issue %s history hit the %d-entry page cap; older events may be missing",
            node["id"],
            HISTORY_PAGE_SIZE,
        )
    events = [*_initial_events(node, created_at), *_born_label_events(node, created_at, names)]
    for entry in history_nodes:
        events.extend(map_history_entry(entry, names))
    canceled_at = node.get("canceledAt")
    if canceled_at:
        # Keyed by time: a reopen-then-recancel carries a new canceledAt and
        # must land as a new event (events are insert-only).
        # ponytail: Canceled -> Todo without a restart leaves this event in
        # place, so the item still reads canceled; emit a reopen signal from
        # history if that ever matters.
        events.append(
            SourceEvent(
                external_id=f"{node['id']}:canceled:{canceled_at}",
                type=EventType.CANCELED,
                occurred_at=datetime.fromisoformat(canceled_at),
            )
        )
    events.extend(_archive_events(node))
    project = node.get("project")
    # completedAt feeds completed_at (the sync synthesizes a missing
    # COMPLETED from it); cancellation arrives as the CANCELED event above.
    completed_at = node.get("completedAt")
    return SourceWorkItem(
        external_id=node["id"],
        title=node["title"],
        # Linear has no story/task/bug field: every item is TASK, and the team's
        # type_labels rule classifies at read time (MetricRules.type_of).
        type=WorkItemType.TASK,
        state=node["state"]["name"],
        state_type=_state_type(node["state"]),
        labels=tuple(_detail(names[i]) for i in node.get("labelIds") or () if i in names),
        parent_external_id=(node.get("parent") or {}).get("id"),
        team_external_id=node["team"]["id"],
        project_external_id=project["id"] if project else None,
        created_at=created_at,
        completed_at=datetime.fromisoformat(completed_at) if completed_at else None,
        events=tuple(events),
        # .get: the field is optional — a node without it must not be dropped as malformed.
        url=node.get("url"),
    )


# Linear state types outside the shared StateType vocabulary, by meaning: a
# Duplicate closes the issue undelivered (Linear also stamps its canceledAt).
_STATE_TYPE_ALIASES = {"duplicate": StateType.CANCELED}


def _state_type(state: dict[str, Any] | None) -> StateType | None:
    """The domain category of a Linear workflow state; None for an unknown type."""
    if state is None:
        return None
    alias = _STATE_TYPE_ALIASES.get(state["type"])
    if alias is not None:
        return alias
    try:
        return StateType(state["type"])
    except ValueError:
        return None


def _archive_events(node: dict[str, Any]) -> list[SourceEvent]:
    """CANCELED at archivedAt for an issue archived while still open.

    Linear hides archived issues: one archived before it was done or
    canceled was abandoned, so it closes undelivered (out of WIP and forecast
    remaining). Closed issues — Linear auto-archives them — keep their
    outcome. Keyed by time like canceledAt, so a re-archive is a new event.

    ponytail: an unarchived issue keeps this event and reads canceled until
    it starts again; emit a reopen from history if unarchiving ever matters.
    """
    archived_at = node.get("archivedAt")
    if not archived_at or _state_type(node["state"]) in (StateType.COMPLETED, StateType.CANCELED):
        return []
    return [
        SourceEvent(
            external_id=f"{node['id']}:archived:{archived_at}",
            type=EventType.CANCELED,
            occurred_at=datetime.fromisoformat(archived_at),
        )
    ]


# Linear's IssueHistory.relationChanges codes are undocumented; decoded
# against a live workspace on 2026-10-04 (spec: sync-captured metric rules).
# On the issue whose history holds the entry: "ab"/"rb" = a "blocked by
# <identifier>" relation added/removed; "br"/"bo" = that blocker resolved/
# reopened (Linear writes them ~0.2 s after the blocker completes or
# reopens). "ax", "rx", "xr", "xo" are the same four seen from the blocker's
# side; "ar"/"rr" (related) and "ad"/"am"/"rd"/"rm" (duplicate) don't block.
# Only the blocked side becomes events, so a blocker never blocks itself.
_BLOCKER_CODES = {
    "ab": EventType.BLOCKER_ADDED,
    "bo": EventType.BLOCKER_ADDED,
    "rb": EventType.BLOCKER_CLEARED,
    "br": EventType.BLOCKER_CLEARED,
}
_NON_BLOCKING_CODES = frozenset({"ax", "rx", "xr", "xo", "ar", "rr", "ad", "am", "rd", "rm"})
# ponytail: warned once per code per process — enough to notice Linear
# adding a code; reset per sync if anyone needs the repeat.
_warned_codes: set[str] = set()


# events.detail is String(255): a longer label name or identifier would fail
# the insert on PostgreSQL.
_DETAIL_MAX = 255


def _detail(text: str) -> str:
    return text[:_DETAIL_MAX]


def _warn_unknown_code(code: str) -> None:
    if "b" in code and code not in _NON_BLOCKING_CODES and code not in _warned_codes:
        _warned_codes.add(code)
        logger.warning("Ignoring unknown Linear relation-change code %r", code)


def _relation_events(entry: dict[str, Any], occurred_at: datetime) -> list[SourceEvent]:
    """Blocked-side "blocked by" relation changes → BLOCKER_ADDED/CLEARED (history only)."""
    events: list[SourceEvent] = []
    for change in entry.get("relationChanges") or ():
        if not isinstance(change, dict):
            continue
        code, identifier = change.get("type"), change.get("identifier")
        if not isinstance(code, str) or not isinstance(identifier, str):
            continue
        event_type = _BLOCKER_CODES.get(code)
        if event_type is None:
            _warn_unknown_code(code)
            continue
        events.append(
            SourceEvent(
                external_id=f"{entry['id']}:blocker:{code}:{identifier}",
                type=event_type,
                occurred_at=occurred_at,
                detail=_detail(identifier),
            )
        )
    return events


_LABEL_CHANGES = (
    ("addedLabelIds", EventType.LABEL_ADDED, "label-added"),
    ("removedLabelIds", EventType.LABEL_REMOVED, "label-removed"),
)


# ponytail: a label event stores the label's name at sync time, so a label
# renamed later keeps its old name on past events. Upgrade path: key events
# by label id and resolve the name at read time.
def _label_events(
    entry: dict[str, Any], occurred_at: datetime, label_names: Mapping[str, str]
) -> list[SourceEvent]:
    """Raw label changes, named; whether a label means blocked is a read-time rule."""
    events: list[SourceEvent] = []
    for key, event_type, suffix in _LABEL_CHANGES:
        for label_id in entry.get(key) or ():
            name = label_names.get(label_id)
            if name is None:
                continue  # a deleted label: no name to match rules against
            events.append(
                SourceEvent(
                    external_id=f"{entry['id']}:{suffix}:{label_id}",
                    type=event_type,
                    occurred_at=occurred_at,
                    detail=_detail(name),
                )
            )
    return events


def _born_label_events(
    node: dict[str, Any], created_at: datetime, label_names: Mapping[str, str]
) -> list[SourceEvent]:
    """LABEL_ADDED at creation for the labels the issue was created with.

    History has no creation entry: a label the issue carries with no add in
    history, or whose first history mention is a removal, was there from
    the start.
    """
    first_was_add: dict[str, bool] = {}
    for entry in sorted(
        node["history"]["nodes"], key=lambda e: datetime.fromisoformat(e["createdAt"])
    ):
        for label_id in entry.get("addedLabelIds") or ():
            first_was_add.setdefault(label_id, True)
        for label_id in entry.get("removedLabelIds") or ():
            first_was_add.setdefault(label_id, False)
    born = {label_id for label_id in node.get("labelIds") or () if label_id not in first_was_add}
    born |= {label_id for label_id, was_add in first_was_add.items() if not was_add}
    return [
        SourceEvent(
            external_id=f"{node['id']}:label-born:{label_id}",
            type=EventType.LABEL_ADDED,
            occurred_at=created_at,
            detail=_detail(label_names[label_id]),
        )
        for label_id in sorted(born)
        if label_id in label_names
    ]


def _transition_events(entry: dict[str, Any], occurred_at: datetime) -> list[SourceEvent]:
    to_state = entry.get("toState")
    if to_state is None:
        return []
    from_state = entry.get("fromState")
    events = [
        SourceEvent(
            external_id=entry["id"],
            type=_event_type(from_state, to_state),
            occurred_at=occurred_at,
            from_state=from_state["name"] if from_state else None,
            to_state=to_state["name"],
            from_state_type=_state_type(from_state),
            to_state_type=_state_type(to_state),
        )
    ]
    if (
        from_state is not None
        and from_state["type"] == "started"
        and to_state["type"] not in ("started", "completed")
    ):
        # Left progress without completing (moved back or canceled).
        events.append(
            SourceEvent(
                external_id=f"{entry['id']}:stopped",
                type=EventType.STOPPED,
                occurred_at=occurred_at,
            )
        )
    return events


def map_history_entry(
    entry: dict[str, Any], label_names: Mapping[str, str] | None = None
) -> list[SourceEvent]:
    """One issue-history entry → 0..n SourceEvents.

    State transitions (with their state types; leaving a started state for a
    non-started, non-completed one also emits a derived STOPPED), raw label
    changes, and blocked-side relation changes. Blocked is decided at read
    time from these (ADR-0011).
    """
    occurred_at = datetime.fromisoformat(entry["createdAt"])
    return [
        *_transition_events(entry, occurred_at),
        *_label_events(entry, occurred_at, label_names or {}),
        *_relation_events(entry, occurred_at),
    ]


def _event_type(from_state: dict[str, Any] | None, to_state: dict[str, Any]) -> EventType:
    from_type = from_state["type"] if from_state else None
    to_type = to_state["type"]
    if to_type == "started" and from_type != "started":
        return EventType.STARTED
    if to_type == "completed" and from_type != "completed":
        return EventType.COMPLETED
    return EventType.STATE_CHANGED
