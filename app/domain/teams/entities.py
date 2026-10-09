from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain._time import utcnow


@dataclass
class Team:
    """A group responsible for delivering software. Teams own Projects and Work Items."""

    organization_id: UUID
    name: str
    external_id: str | None = None
    # When a sync last pulled this team's work items from the source; None
    # if never. Dates the team's data even when the sync brought no events.
    last_synced_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        stripped = self.name.strip()
        if not stripped:
            raise ValueError("Team name must not be empty")
        self.name = stripped
