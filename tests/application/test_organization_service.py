from app.application.organizations.service import OrganizationService
from tests.fakes import InMemoryOrganizationRepository


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
