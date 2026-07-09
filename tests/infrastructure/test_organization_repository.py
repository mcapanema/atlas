from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.organizations.entities import Organization
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository


async def test_add_and_list_roundtrip(session: AsyncSession) -> None:
    repo = SqlAlchemyOrganizationRepository(session)
    org = Organization(name="Acme")

    await repo.add(org)
    result = await repo.list()

    assert [o.id for o in result] == [org.id]
    assert result[0].name == "Acme"


async def test_get_returns_none_for_unknown_id(session: AsyncSession) -> None:
    repo = SqlAlchemyOrganizationRepository(session)

    assert await repo.get(uuid4()) is None


async def test_get_returns_stored_organization(session: AsyncSession) -> None:
    repo = SqlAlchemyOrganizationRepository(session)
    org = Organization(name="Beta")
    await repo.add(org)

    fetched = await repo.get(org.id)

    assert fetched is not None
    assert fetched.id == org.id
    assert fetched.name == "Beta"
