from uuid import UUID

from app.domain.projects.entities import Project
from app.domain.projects.repository import ProjectRepository
from app.domain.work_items.repository import WorkItemRepository


class ProjectService:
    """Application use cases for Projects."""

    def __init__(self, repository: ProjectRepository, work_items: WorkItemRepository) -> None:
        self._repository = repository
        self._work_items = work_items

    async def create_project(
        self, team_id: UUID, name: str, external_id: str | None = None
    ) -> Project:
        project = Project(team_id=team_id, name=name, external_id=external_id)
        await self._repository.add(project)
        return project

    async def list_projects(self) -> list[Project]:
        return await self._repository.list()

    async def list_projects_with_teams(self) -> list[tuple[Project, list[UUID]]]:
        """Each project with every team it spans: its home team first, then the rest by id."""
        teams_by_project = await self._work_items.team_ids_by_project()
        return [
            (
                project,
                [
                    project.team_id,
                    *sorted(
                        teams_by_project.get(project.id, frozenset()) - {project.team_id}, key=str
                    ),
                ],
            )
            for project in await self._repository.list()
        ]

    async def get_project(self, project_id: UUID) -> Project | None:
        return await self._repository.get(project_id)
