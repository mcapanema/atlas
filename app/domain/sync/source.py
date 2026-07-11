"""Platform-neutral snapshots of an external delivery system.

Connectors (Infrastructure) produce these; the sync use case (Application)
consumes them. They carry external identity only — internal UUIDs are
resolved during sync.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.events.entities import EventType
from app.domain.work_items.entities import WorkItemType


@dataclass(frozen=True)
class SourceTeam:
    external_id: str
    name: str


@dataclass(frozen=True)
class SourceProject:
    external_id: str
    name: str
    team_external_id: str | None


@dataclass(frozen=True)
class SourceEvent:
    external_id: str
    type: EventType
    occurred_at: datetime
    from_state: str | None = None
    to_state: str | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("SourceEvent.occurred_at must be timezone-aware")


@dataclass(frozen=True)
class SourceWorkItem:
    external_id: str
    title: str
    type: WorkItemType
    state: str
    team_external_id: str
    project_external_id: str | None
    created_at: datetime
    # When the source system says the item reached a done state — set even
    # when the event history (e.g. a truncated changelog) never recorded a
    # completion. Sync uses the mismatch to synthesize the terminal event.
    completed_at: datetime | None = None
    events: tuple[SourceEvent, ...] = ()
