from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain._time import utcnow


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
    STATE_CHANGED = "state_changed"


@dataclass(frozen=True)
class Event:
    """An immutable record of something that occurred during delivery of a Work Item."""

    work_item_id: UUID
    type: EventType
    occurred_at: datetime
    from_state: str | None = None
    to_state: str | None = None
    external_id: str | None = None
    id: UUID = field(default_factory=uuid4)
    recorded_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("Event.occurred_at must be timezone-aware")
