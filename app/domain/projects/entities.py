from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain._time import utcnow


@dataclass
class Project:
    """A collection of Work Items executed to deliver business value. Owned by a Team."""

    team_id: UUID
    name: str
    external_id: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        stripped = self.name.strip()
        if not stripped:
            raise ValueError("Project name must not be empty")
        self.name = stripped
