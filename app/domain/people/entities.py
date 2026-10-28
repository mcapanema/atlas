from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain._time import utcnow


@dataclass
class Person:
    """Someone work is assigned to — synced from a source system or created locally."""

    organization_id: UUID
    name: str
    external_id: str | None = None
    email: str | None = None
    # Manual override of `name` (e.g. to restore accents); blank means no override.
    display_name: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        stripped = self.name.strip()
        if not stripped:
            raise ValueError("Person name must not be empty")
        self.name = stripped
        self.display_name = (self.display_name or "").strip() or None

    @property
    def shown_name(self) -> str:
        return self.display_name or self.name
