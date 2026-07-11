from uuid import uuid4

from app.application.projects.service import ProjectService
from tests.fakes import InMemoryProjectRepository


async def test_create_project_persists_and_returns() -> None:
    repo = InMemoryProjectRepository()
    service = ProjectService(repo)
    team_id = uuid4()

    project = await service.create_project(team_id=team_id, name="Checkout")

    assert project.team_id == team_id
    assert project.name == "Checkout"
    assert await repo.get(project.id) is project


async def test_list_projects_returns_all() -> None:
    repo = InMemoryProjectRepository()
    service = ProjectService(repo)
    await service.create_project(team_id=uuid4(), name="Checkout")
    await service.create_project(team_id=uuid4(), name="Search")

    projects = await service.list_projects()

    assert {p.name for p in projects} == {"Checkout", "Search"}


async def test_get_project_returns_none_for_unknown_id() -> None:
    service = ProjectService(InMemoryProjectRepository())

    assert await service.get_project(uuid4()) is None


async def test_get_project_returns_created_project() -> None:
    repo = InMemoryProjectRepository()
    service = ProjectService(repo)
    project = await service.create_project(team_id=uuid4(), name="Checkout")

    assert await service.get_project(project.id) is project
