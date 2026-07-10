from typing import Protocol
from uuid import UUID

from app.domain.projects.entities import Project


class ProjectRepository(Protocol):
    """Port for persisting and retrieving Projects. Implemented in Infrastructure."""

    async def add(self, project: Project) -> None: ...

    async def update(self, project: Project) -> None: ...

    async def list(self) -> list[Project]: ...

    async def get(self, project_id: UUID) -> Project | None: ...

    async def get_by_external_id(self, external_id: str) -> Project | None: ...
