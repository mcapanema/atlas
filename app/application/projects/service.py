from uuid import UUID

from app.domain.projects.entities import Project
from app.domain.projects.repository import ProjectRepository


class ProjectService:
    """Application use cases for Projects."""

    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    async def create_project(
        self, team_id: UUID, name: str, external_id: str | None = None
    ) -> Project:
        project = Project(team_id=team_id, name=name, external_id=external_id)
        await self._repository.add(project)
        return project

    async def list_projects(self) -> list[Project]:
        return await self._repository.list()

    async def get_project(self, project_id: UUID) -> Project | None:
        return await self._repository.get(project_id)
