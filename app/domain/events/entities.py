from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain._time import utcnow
from app.domain.work_items.entities import StateType


class EventType(StrEnum):
    """An immutable delivery occurrence. The system of record; metrics derive from these."""

    CREATED = "created"
    ASSIGNED = "assigned"
    STARTED = "started"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    REVIEW = "review"
    MERGED = "merged"
    COMPLETED = "completed"
    # Left a started state without completing (moved back, or canceled from
    # progress) — ends WIP; a later STARTED resumes it.
    STOPPED = "stopped"
    # Closed without delivery. After a COMPLETED it changes nothing.
    CANCELED = "canceled"
    STATE_CHANGED = "state_changed"
    # A raw label change; detail = the label's name. Whether it means
    # blocked is a read-time rule (MetricRules.is_blocked_label).
    LABEL_ADDED = "label_added"
    LABEL_REMOVED = "label_removed"
    # A "blocked by" relation opened (added, or its blocker reopened) or
    # cleared (removed, or its blocker resolved); detail = the blocker's
    # identifier, e.g. "DEP-1309".
    BLOCKER_ADDED = "blocker_added"
    BLOCKER_CLEARED = "blocker_cleared"


@dataclass(frozen=True)
class Event:
    """An immutable record of something that occurred during delivery of a Work Item."""

    work_item_id: UUID
    type: EventType
    occurred_at: datetime
    from_state: str | None = None
    to_state: str | None = None
    external_id: str | None = None
    # Categories of from_state/to_state on a state transition; None when
    # unknown (REST-created events, or not filled yet — ADR-0011).
    from_state_type: StateType | None = None
    to_state_type: StateType | None = None
    # Label name (label events) or blocker identifier (blocker events).
    detail: str | None = None
    id: UUID = field(default_factory=uuid4)
    recorded_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("Event.occurred_at must be timezone-aware")


# Same-instant events replay in lifecycle order — a start precedes the
# finish it led to. Linear automations can write several transitions with
# one timestamp, and storage order must not decide whether an item is done.
# ponytail: a genuine same-instant finish-then-reopen would read done; order
# by the from/to state chain if that ever shows up in real data.
_SAME_INSTANT_RANK = {EventType.CREATED: 0, EventType.STARTED: 1}


def event_order(event: Event) -> tuple[datetime, int]:
    """Sort key: chronological; ties go CREATED, STARTED, then the rest."""
    return event.occurred_at, _SAME_INSTANT_RANK.get(event.type, 2)
