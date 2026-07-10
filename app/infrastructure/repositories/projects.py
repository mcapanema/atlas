from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Uuid

from app.domain.projects.entities import Project
from app.infrastructure.database.base import Base


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    team_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("teams.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def to_domain(self) -> Project:
        return Project(
            id=self.id,
            team_id=self.team_id,
            name=self.name,
            external_id=self.external_id,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, project: Project) -> "ProjectModel":
        return cls(
            id=project.id,
            team_id=project.team_id,
            name=project.name,
            external_id=project.external_id,
            created_at=project.created_at,
        )


class SqlAlchemyProjectRepository:
    """SQLAlchemy adapter for the ProjectRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, project: Project) -> None:
        self._session.add(ProjectModel.from_domain(project))
        await self._session.flush()

    async def update(self, project: Project) -> None:
        await self._session.merge(ProjectModel.from_domain(project))
        await self._session.flush()

    async def list(self) -> list[Project]:
        result = await self._session.execute(
            select(ProjectModel).order_by(ProjectModel.created_at)
        )
        return [model.to_domain() for model in result.scalars()]

    async def get(self, project_id: UUID) -> Project | None:
        model = await self._session.get(ProjectModel, project_id)
        return model.to_domain() if model is not None else None

    async def get_by_external_id(self, external_id: str) -> Project | None:
        result = await self._session.execute(
            select(ProjectModel).where(ProjectModel.external_id == external_id)
        )
        model = result.scalars().one_or_none()
        return model.to_domain() if model is not None else None
