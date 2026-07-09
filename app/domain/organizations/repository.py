from typing import Protocol
from uuid import UUID

from app.domain.organizations.entities import Organization


class OrganizationRepository(Protocol):
    """Port for persisting and retrieving Organizations. Implemented in Infrastructure."""

    async def add(self, organization: Organization) -> None: ...

    async def list(self) -> list[Organization]: ...

    async def get(self, organization_id: UUID) -> Organization | None: ...
