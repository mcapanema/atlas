from collections.abc import Collection
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, column_property, mapped_column
from sqlalchemy.types import Uuid

from app.domain.work_items.entities import StateType, WorkItem, WorkItemType
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime
from app.infrastructure.repositories.batching import chunked
from app.infrastructure.repositories.people import PersonModel


class WorkItemModel(Base):
    __tablename__ = "work_items"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    team_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("teams.id"), nullable=False, index=True)
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    state_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    labels: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("work_items.id", name="fk_work_items_parent_id"), nullable=True, index=True
    )
    assignee_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("people.id", name="fk_work_items_assignee_id"), nullable=True, index=True
    )
    # Read-only: the assignee's shown name, resolved by a correlated subquery on load.
    assignee_name: Mapped[str | None] = column_property(
        select(func.coalesce(PersonModel.display_name, PersonModel.name))
        .where(PersonModel.id == assignee_id)
        .correlate_except(PersonModel)
        .scalar_subquery()
    )

    def to_domain(self) -> WorkItem:
        return WorkItem(
            id=self.id,
            team_id=self.team_id,
            project_id=self.project_id,
            title=self.title,
            type=WorkItemType(self.type),
            state=self.state,
            external_id=self.external_id,
            url=self.url,
            key=self.key,
            created_at=self.created_at,
            state_type=StateType(self.state_type) if self.state_type else None,
            labels=tuple(self.labels),
            parent_id=self.parent_id,
            assignee=self.assignee_name,
            assignee_id=self.assignee_id,
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
            url=work_item.url,
            key=work_item.key,
            created_at=work_item.created_at,
            state_type=work_item.state_type.value if work_item.state_type else None,
            labels=list(work_item.labels),
            parent_id=work_item.parent_id,
            assignee_id=work_item.assignee_id,
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

    async def delete(self, work_item_ids: list[UUID]) -> None:
        for chunk in chunked(work_item_ids):
            # Children outlive a deleted parent: drop the link first (FKs are enforced).
            await self._session.execute(
                update(WorkItemModel)
                .where(WorkItemModel.parent_id.in_(chunk))
                .values(parent_id=None)
            )
            await self._session.execute(delete(WorkItemModel).where(WorkItemModel.id.in_(chunk)))

    async def get_by_keys(
        self, keys: list[str], *, team_ids: Collection[UUID]
    ) -> dict[str, WorkItem]:
        found: dict[str, WorkItem] = {}
        if not team_ids:
            return found
        for chunk in chunked(keys):
            result = await self._session.execute(
                select(WorkItemModel).where(
                    WorkItemModel.key.in_(chunk), WorkItemModel.team_id.in_(team_ids)
                )
            )
            for model in result.scalars():
                # A stale duplicate may exist inside the teams; one row is kept.
                if model.key is not None:
                    found[model.key] = model.to_domain()
        return found

    # Must stay above `list` — that method shadows the `list` builtin for every
    # annotation below it in this class body, so `-> list[str]` would fail.
    async def list_states(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[str]:
        query = select(WorkItemModel.state).distinct().order_by(WorkItemModel.state)
        if team_id is not None:
            query = query.where(WorkItemModel.team_id == team_id)
        if project_id is not None:
            query = query.where(WorkItemModel.project_id == project_id)
        result = await self._session.execute(query)
        return list(result.scalars())

    async def list_labels(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[str]:
        query = select(WorkItemModel.labels)
        if team_id is not None:
            query = query.where(WorkItemModel.team_id == team_id)
        if project_id is not None:
            query = query.where(WorkItemModel.project_id == project_id)
        result = await self._session.execute(query)
        # ponytail: flattened in Python — JSON array functions differ between
        # SQLite and PostgreSQL. Push down if a scope outgrows one column scan.
        return sorted({label for labels in result.scalars() for label in labels})

    async def parent_ids(self) -> set[UUID]:
        result = await self._session.execute(
            select(WorkItemModel.parent_id).where(WorkItemModel.parent_id.is_not(None)).distinct()
        )
        return {parent_id for parent_id in result.scalars() if parent_id is not None}

    async def team_ids_by_project(self) -> dict[UUID, frozenset[UUID]]:
        result = await self._session.execute(
            select(WorkItemModel.project_id, WorkItemModel.team_id)
            .distinct()
            .where(WorkItemModel.project_id.is_not(None))
        )
        teams: dict[UUID, set[UUID]] = {}
        for project_id, team_id in result.all():
            if project_id is not None:
                teams.setdefault(project_id, set()).add(team_id)
        return {project_id: frozenset(ids) for project_id, ids in teams.items()}

    async def list(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkItem]:
        query = select(WorkItemModel)
        if team_id is not None:
            query = query.where(WorkItemModel.team_id == team_id)
        if project_id is not None:
            query = query.where(WorkItemModel.project_id == project_id)
        # id tiebreak keeps pages stable when created_at collides
        query = query.order_by(WorkItemModel.created_at, WorkItemModel.id)
        if offset:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        result = await self._session.execute(query)
        return [model.to_domain() for model in result.scalars()]

    async def count(self, *, team_id: UUID | None = None, project_id: UUID | None = None) -> int:
        query = select(func.count()).select_from(WorkItemModel)
        if team_id is not None:
            query = query.where(WorkItemModel.team_id == team_id)
        if project_id is not None:
            query = query.where(WorkItemModel.project_id == project_id)
        result = await self._session.execute(query)
        return int(result.scalar_one())

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        model = await self._session.get(WorkItemModel, work_item_id)
        return model.to_domain() if model is not None else None

    async def get_by_external_id(self, external_id: str) -> WorkItem | None:
        result = await self._session.execute(
            select(WorkItemModel).where(WorkItemModel.external_id == external_id)
        )
        model = result.scalars().one_or_none()
        return model.to_domain() if model is not None else None
