from typing import Protocol
from uuid import UUID

from app.domain.incidents.entities import ServiceIncident


class ServiceIncidentRepository(Protocol):
    """Port for persisting ServiceIncidents. Implemented in Infrastructure."""

    async def add(self, incident: ServiceIncident) -> None: ...

    async def update(self, incident: ServiceIncident) -> None: ...

    async def get_by_external_ids(self, external_ids: list[str]) -> dict[str, ServiceIncident]:
        """Across organizations: an external id is unique."""
        ...

    async def list(self, organization_id: UUID) -> list[ServiceIncident]: ...
