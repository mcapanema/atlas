from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain._time import require_aware


@dataclass
class ServiceIncident:
    """An incident reported by an incident tracker, kept for the failure and restore metrics.

    Mutable: it is restored after creation. `organization_id` is the
    organization that first synced it.
    """

    organization_id: UUID
    external_id: str
    title: str
    opened_at: datetime
    restored_at: datetime | None = None
    services: tuple[str, ...] = ()
    severity: str | None = None
    url: str | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        require_aware("ServiceIncident", opened_at=self.opened_at, restored_at=self.restored_at)
        if self.restored_at is not None and self.restored_at < self.opened_at:
            raise ValueError("ServiceIncident.restored_at must not be before opened_at")
