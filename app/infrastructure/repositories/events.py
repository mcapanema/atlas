from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, select
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, TypeDecorator, Uuid

from app.domain.events.entities import Event, EventType
from app.infrastructure.database.base import Base


class _UTCDateTime(TypeDecorator[datetime]):
    """DateTime(timezone=True) that survives SQLite's naive round-trip.

    ponytail: SQLite stores DATETIME as a naive ISO string, dropping tzinfo
    on read (Postgres's timestamptz doesn't have this problem). Event's
    domain invariant requires tz-aware occurred_at, so reattach UTC here.
    Move to a shared database/types.py if another entity needs the same fix.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    work_item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("work_items.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(_UTCDateTime, nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(_UTCDateTime, nullable=False)

    def to_domain(self) -> Event:
        return Event(
            id=self.id,
            work_item_id=self.work_item_id,
            type=EventType(self.type),
            occurred_at=self.occurred_at,
            from_state=self.from_state,
            to_state=self.to_state,
            external_id=self.external_id,
            recorded_at=self.recorded_at,
        )

    @classmethod
    def from_domain(cls, event: Event) -> "EventModel":
        return cls(
            id=event.id,
            work_item_id=event.work_item_id,
            type=event.type.value,
            occurred_at=event.occurred_at,
            from_state=event.from_state,
            to_state=event.to_state,
            external_id=event.external_id,
            recorded_at=event.recorded_at,
        )


class SqlAlchemyEventRepository:
    """SQLAlchemy adapter for the EventRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: Event) -> None:
        self._session.add(EventModel.from_domain(event))
        await self._session.flush()

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]:
        result = await self._session.execute(
            select(EventModel)
            .where(EventModel.work_item_id == work_item_id)
            .order_by(EventModel.occurred_at)
        )
        return [model.to_domain() for model in result.scalars()]

    async def list_for_work_items(self, work_item_ids: list[UUID]) -> list[Event]:
        if not work_item_ids:
            return []
        result = await self._session.execute(
            select(EventModel)
            .where(EventModel.work_item_id.in_(work_item_ids))
            .order_by(EventModel.occurred_at)
        )
        return [model.to_domain() for model in result.scalars()]

    async def get_by_external_id(self, external_id: str) -> Event | None:
        result = await self._session.execute(
            select(EventModel).where(EventModel.external_id == external_id)
        )
        model = result.scalars().one_or_none()
        return model.to_domain() if model is not None else None
