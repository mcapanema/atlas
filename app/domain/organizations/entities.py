from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain._time import utcnow


@dataclass
class Organization:
    """A company using the platform — the root of the delivery hierarchy."""

    name: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        stripped = self.name.strip()
        if not stripped:
            raise ValueError("Organization name must not be empty")
        self.name = stripped
