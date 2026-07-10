from uuid import UUID, uuid4

from app.application.projects.service import ProjectService
from app.domain.projects.entities import Project


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self._projects: dict[UUID, Project] = {}

    async def add(self, project: Project) -> None:
        self._projects[project.id] = project

    async def update(self, project: Project) -> None:
        self._projects[project.id] = project

    async def list(self) -> list[Project]:
        return list(self._projects.values())

    async def get(self, project_id: UUID) -> Project | None:
        return self._projects.get(project_id)

    async def get_by_external_id(self, external_id: str) -> Project | None:
        return next(
            (p for p in self._projects.values() if p.external_id == external_id), None
        )


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
