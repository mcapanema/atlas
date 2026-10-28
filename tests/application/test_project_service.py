from uuid import uuid4

from app.application.projects.service import ProjectService
from app.domain.work_items.entities import WorkItem
from tests.fakes import InMemoryProjectRepository, InMemoryWorkItemRepository


async def test_create_project_persists_and_returns() -> None:
    repo = InMemoryProjectRepository()
    service = ProjectService(repo, InMemoryWorkItemRepository())
    team_id = uuid4()

    project = await service.create_project(team_id=team_id, name="Checkout")

    assert project.team_id == team_id
    assert project.name == "Checkout"
    assert await repo.get(project.id) is project


async def test_list_projects_returns_all() -> None:
    repo = InMemoryProjectRepository()
    service = ProjectService(repo, InMemoryWorkItemRepository())
    await service.create_project(team_id=uuid4(), name="Checkout")
    await service.create_project(team_id=uuid4(), name="Search")

    projects = await service.list_projects()

    assert {p.name for p in projects} == {"Checkout", "Search"}


async def test_get_project_returns_none_for_unknown_id() -> None:
    service = ProjectService(InMemoryProjectRepository(), InMemoryWorkItemRepository())

    assert await service.get_project(uuid4()) is None


async def test_get_project_returns_created_project() -> None:
    repo = InMemoryProjectRepository()
    service = ProjectService(repo, InMemoryWorkItemRepository())
    project = await service.create_project(team_id=uuid4(), name="Checkout")

    assert await service.get_project(project.id) is project


async def test_list_projects_with_teams_puts_home_team_first_then_sorted_others() -> None:
    projects, items = InMemoryProjectRepository(), InMemoryWorkItemRepository()
    service = ProjectService(projects, items)
    home = uuid4()
    project = await service.create_project(team_id=home, name="Apollo")
    empty = await service.create_project(team_id=uuid4(), name="Empty")
    others = sorted([uuid4(), uuid4()], key=str)
    for team_id in [others[1], home, others[0]]:
        await items.add(WorkItem(team_id=team_id, title="x", project_id=project.id))

    listed = {p.name: ids for p, ids in await service.list_projects_with_teams()}

    assert listed["Apollo"] == [home, *others]
    assert listed["Empty"] == [empty.team_id]
