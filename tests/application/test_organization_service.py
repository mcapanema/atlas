from uuid import UUID

from app.application.organizations.service import OrganizationService
from app.domain.organizations.entities import Organization


class InMemoryOrganizationRepository:
    """Test double implementing the OrganizationRepository port."""

    def __init__(self) -> None:
        self._store: dict[UUID, Organization] = {}

    async def add(self, organization: Organization) -> None:
        self._store[organization.id] = organization

    async def list(self) -> list[Organization]:
        return list(self._store.values())

    async def get(self, organization_id: UUID) -> Organization | None:
        return self._store.get(organization_id)


async def test_create_organization_persists_and_returns() -> None:
    repo = InMemoryOrganizationRepository()
    service = OrganizationService(repo)

    created = await service.create_organization("Acme")

    assert created.name == "Acme"
    assert await repo.get(created.id) == created


async def test_list_organizations_returns_all() -> None:
    repo = InMemoryOrganizationRepository()
    service = OrganizationService(repo)
    await service.create_organization("Acme")
    await service.create_organization("Beta")

    names = sorted(o.name for o in await service.list_organizations())

    assert names == ["Acme", "Beta"]
