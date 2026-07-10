from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from app.infrastructure.repositories.projects import SqlAlchemyProjectRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository


async def _team_id(session: AsyncSession) -> UUID:
    """FK enforcement is on (see conftest) — projects need a real team."""
    team = Team(organization_id=uuid4(), name="Platform")
    await SqlAlchemyTeamRepository(session).add(team)
    return team.id


async def test_add_then_get(session: AsyncSession) -> None:
    repo = SqlAlchemyProjectRepository(session)
    project = Project(team_id=await _team_id(session), name="Checkout", external_id="lin_p1")

    await repo.add(project)
    fetched = await repo.get(project.id)

    assert fetched is not None
    assert fetched.name == "Checkout"
    assert fetched.team_id == project.team_id
    assert fetched.external_id == "lin_p1"


async def test_get_by_external_id(session: AsyncSession) -> None:
    repo = SqlAlchemyProjectRepository(session)
    project = Project(team_id=await _team_id(session), name="Checkout", external_id="lin_p1")
    await repo.add(project)

    fetched = await repo.get_by_external_id("lin_p1")

    assert fetched is not None and fetched.id == project.id
    assert await repo.get_by_external_id("nope") is None


async def test_list_returns_all(session: AsyncSession) -> None:
    repo = SqlAlchemyProjectRepository(session)
    await repo.add(Project(team_id=await _team_id(session), name="Checkout"))
    await repo.add(Project(team_id=await _team_id(session), name="Search"))

    projects = await repo.list()

    assert {p.name for p in projects} == {"Checkout", "Search"}


async def test_update_persists_changed_fields(session: AsyncSession) -> None:
    repo = SqlAlchemyProjectRepository(session)
    project = Project(team_id=await _team_id(session), name="Checkout", external_id="lin_p1")
    await repo.add(project)

    project.name = "Checkout v2"
    await repo.update(project)

    fetched = await repo.get(project.id)
    assert fetched is not None
    assert fetched.name == "Checkout v2"
