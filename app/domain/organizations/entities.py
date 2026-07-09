from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Organization:
    """A company using the platform — the root of the delivery hierarchy."""

    name: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        stripped = self.name.strip()
        if not stripped:
            raise ValueError("Organization name must not be empty")
        self.name = stripped
