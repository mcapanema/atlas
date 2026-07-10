from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem, WorkItemType
from app.infrastructure.repositories.projects import SqlAlchemyProjectRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository


async def _team_id(session: AsyncSession) -> UUID:
    """FK enforcement is on (see conftest) — work items need a real team."""
    team = Team(organization_id=uuid4(), name="Platform")
    await SqlAlchemyTeamRepository(session).add(team)
    return team.id


async def _project_id(session: AsyncSession, team_id: UUID) -> UUID:
    project = Project(team_id=team_id, name="Checkout")
    await SqlAlchemyProjectRepository(session).add(project)
    return project.id


async def test_add_then_get_roundtrips_enum(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(
        team_id=await _team_id(session),
        title="Add login",
        type=WorkItemType.BUG,
        state="in_progress",
    )

    await repo.add(item)
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.title == "Add login"
    assert fetched.type is WorkItemType.BUG
    assert fetched.state == "in_progress"


async def test_get_by_external_id(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(team_id=await _team_id(session), title="Add login", external_id="lin_i1")
    await repo.add(item)

    fetched = await repo.get_by_external_id("lin_i1")

    assert fetched is not None and fetched.id == item.id
    assert await repo.get_by_external_id("nope") is None


async def test_list_filters_by_team_and_project(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_a, team_b = await _team_id(session), await _team_id(session)
    project = await _project_id(session, team_a)
    await repo.add(WorkItem(team_id=team_a, title="A", project_id=project))
    await repo.add(WorkItem(team_id=team_a, title="B"))
    await repo.add(WorkItem(team_id=team_b, title="C"))

    assert {i.title for i in await repo.list(team_id=team_a)} == {"A", "B"}
    assert {i.title for i in await repo.list(project_id=project)} == {"A"}
    assert {i.title for i in await repo.list()} == {"A", "B", "C"}


async def test_update_persists_changed_fields(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    item = WorkItem(team_id=team_id, title="Add login", state="backlog")
    await repo.add(item)

    new_project_id = await _project_id(session, team_id)
    item.state = "In Progress"
    item.project_id = new_project_id
    await repo.update(item)

    fetched = await repo.get(item.id)
    assert fetched is not None
    assert fetched.state == "In Progress"
    assert fetched.project_id == new_project_id
