from app.domain.organizations.entities import Organization
from app.domain.organizations.repository import OrganizationRepository


class OrganizationService:
    """Application use cases for Organizations."""

    def __init__(self, repository: OrganizationRepository) -> None:
        self._repository = repository

    async def create_organization(self, name: str) -> Organization:
        organization = Organization(name=name)
        await self._repository.add(organization)
        return organization

    async def list_organizations(self) -> list[Organization]:
        return await self._repository.list()
