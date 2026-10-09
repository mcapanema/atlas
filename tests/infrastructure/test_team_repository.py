from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.teams.entities import Team
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository


async def test_add_then_get(session: AsyncSession) -> None:
    repo = SqlAlchemyTeamRepository(session)
    team = Team(organization_id=uuid4(), name="Platform", external_id="lin_1")

    await repo.add(team)
    fetched = await repo.get(team.id)

    assert fetched is not None
    assert fetched.name == "Platform"
    assert fetched.external_id == "lin_1"
    assert fetched.organization_id == team.organization_id


async def test_get_missing_returns_none(session: AsyncSession) -> None:
    repo = SqlAlchemyTeamRepository(session)

    assert await repo.get(uuid4()) is None


async def test_get_by_external_id(session: AsyncSession) -> None:
    repo = SqlAlchemyTeamRepository(session)
    team = Team(organization_id=uuid4(), name="Platform", external_id="lin_1")
    await repo.add(team)

    fetched = await repo.get_by_external_id("lin_1")

    assert fetched is not None
    assert fetched.id == team.id
    assert await repo.get_by_external_id("nope") is None


async def test_list_returns_all(session: AsyncSession) -> None:
    repo = SqlAlchemyTeamRepository(session)
    await repo.add(Team(organization_id=uuid4(), name="Platform"))
    await repo.add(Team(organization_id=uuid4(), name="Growth"))

    teams = await repo.list()

    assert {t.name for t in teams} == {"Platform", "Growth"}


async def test_update_persists_changed_fields(session: AsyncSession) -> None:
    repo = SqlAlchemyTeamRepository(session)
    team = Team(organization_id=uuid4(), name="Platform", external_id="lin_1")
    await repo.add(team)

    team.name = "Platform Engineering"
    await repo.update(team)

    fetched = await repo.get(team.id)
    assert fetched is not None
    assert fetched.name == "Platform Engineering"


async def test_mark_synced_stamps_only_the_given_teams(session: AsyncSession) -> None:
    repo = SqlAlchemyTeamRepository(session)
    synced = Team(organization_id=uuid4(), name="Platform")
    other = Team(organization_id=synced.organization_id, name="Mobile")
    await repo.add(synced)
    await repo.add(other)
    at = datetime(2026, 10, 9, 14, 30, tzinfo=UTC)

    await repo.mark_synced([synced.id], at)

    fetched, untouched = await repo.get(synced.id), await repo.get(other.id)
    assert fetched is not None
    assert untouched is not None
    assert fetched.last_synced_at == at
    assert untouched.last_synced_at is None
