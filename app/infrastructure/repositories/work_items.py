from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Uuid

from app.domain.work_items.entities import WorkItem, WorkItemType
from app.infrastructure.database.base import Base


class WorkItemModel(Base):
    __tablename__ = "work_items"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    team_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("teams.id"), nullable=False, index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def to_domain(self) -> WorkItem:
        return WorkItem(
            id=self.id,
            team_id=self.team_id,
            project_id=self.project_id,
            title=self.title,
            type=WorkItemType(self.type),
            state=self.state,
            external_id=self.external_id,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, work_item: WorkItem) -> "WorkItemModel":
        return cls(
            id=work_item.id,
            team_id=work_item.team_id,
            project_id=work_item.project_id,
            title=work_item.title,
            type=work_item.type.value,
            state=work_item.state,
            external_id=work_item.external_id,
            created_at=work_item.created_at,
        )


class SqlAlchemyWorkItemRepository:
    """SQLAlchemy adapter for the WorkItemRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, work_item: WorkItem) -> None:
        self._session.add(WorkItemModel.from_domain(work_item))
        await self._session.flush()

    async def update(self, work_item: WorkItem) -> None:
        await self._session.merge(WorkItemModel.from_domain(work_item))
        await self._session.flush()

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[WorkItem]:
        query = select(WorkItemModel)
        if team_id is not None:
            query = query.where(WorkItemModel.team_id == team_id)
        if project_id is not None:
            query = query.where(WorkItemModel.project_id == project_id)
        result = await self._session.execute(query.order_by(WorkItemModel.created_at))
        return [model.to_domain() for model in result.scalars()]

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        model = await self._session.get(WorkItemModel, work_item_id)
        return model.to_domain() if model is not None else None

    async def get_by_external_id(self, external_id: str) -> WorkItem | None:
        result = await self._session.execute(
            select(WorkItemModel).where(WorkItemModel.external_id == external_id)
        )
        model = result.scalars().one_or_none()
        return model.to_domain() if model is not None else None
