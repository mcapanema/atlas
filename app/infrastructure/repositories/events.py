from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    CursorResult,
    ForeignKey,
    String,
    and_,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.events.entities import Event, EventType
from app.domain.work_items.entities import StateType
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime
from app.infrastructure.repositories.batching import chunked


def _state_type(value: str | None) -> StateType | None:
    return StateType(value) if value is not None else None


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    work_item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("work_items.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_state_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_state_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> Event:
        return Event(
            id=self.id,
            work_item_id=self.work_item_id,
            type=EventType(self.type),
            occurred_at=self.occurred_at,
            from_state=self.from_state,
            to_state=self.to_state,
            from_state_type=_state_type(self.from_state_type),
            to_state_type=_state_type(self.to_state_type),
            detail=self.detail,
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
            from_state_type=event.from_state_type.value if event.from_state_type else None,
            to_state_type=event.to_state_type.value if event.to_state_type else None,
            detail=event.detail,
            external_id=event.external_id,
            recorded_at=event.recorded_at,
        )


# A stored transition whose state types are still unknown (ADR-0011): no
# to-type, or a from state whose type had no mapping when it was stored.
_TO_UNTYPED = EventModel.to_state_type.is_(None)
_FROM_UNTYPED = and_(EventModel.from_state.is_not(None), EventModel.from_state_type.is_(None))


class SqlAlchemyEventRepository:
    """SQLAlchemy adapter for the EventRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: Event) -> None:
        self._session.add(EventModel.from_domain(event))
        await self._session.flush()

    async def delete_for_work_items(self, work_item_ids: list[UUID]) -> None:
        for chunk in chunked(work_item_ids):
            await self._session.execute(
                delete(EventModel).where(EventModel.work_item_id.in_(chunk))
            )

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]:
        result = await self._session.execute(
            select(EventModel)
            .where(EventModel.work_item_id == work_item_id)
            .order_by(EventModel.occurred_at)
        )
        return [model.to_domain() for model in result.scalars()]

    async def list_for_work_items(self, work_item_ids: list[UUID]) -> list[Event]:
        events: list[Event] = []
        for chunk in chunked(work_item_ids):
            result = await self._session.execute(
                select(EventModel).where(EventModel.work_item_id.in_(chunk))
            )
            events.extend(model.to_domain() for model in result.scalars())
        # per-chunk ORDER BY can't order across chunks — sort the merged list
        events.sort(key=lambda event: event.occurred_at)
        return events

    async def get_by_external_id(self, external_id: str) -> Event | None:
        result = await self._session.execute(
            select(EventModel).where(EventModel.external_id == external_id)
        )
        model = result.scalars().one_or_none()
        return model.to_domain() if model is not None else None

    async def existing_external_ids(self, external_ids: list[str]) -> set[str]:
        found: set[str] = set()
        for chunk in chunked(external_ids):
            result = await self._session.execute(
                select(EventModel.external_id).where(EventModel.external_id.in_(chunk))
            )
            for external_id in result.scalars():
                if external_id is not None:
                    found.add(external_id)
        return found

    async def external_ids_missing_state_types(self, external_ids: list[str]) -> set[str]:
        found: set[str] = set()
        for chunk in chunked(external_ids):
            result = await self._session.execute(
                select(EventModel.external_id).where(
                    EventModel.external_id.in_(chunk), or_(_TO_UNTYPED, _FROM_UNTYPED)
                )
            )
            found.update(eid for eid in result.scalars() if eid is not None)
        return found

    async def fill_state_types(
        self, types_by_external_id: Mapping[str, tuple[StateType | None, StateType | None]]
    ) -> int:
        # ponytail: one UPDATE per event — only the first sync after ADR-0011
        # has rows to fill (~50k worst case, seconds on SQLite). Batch with a
        # CASE expression if a bigger workspace ever makes it slow.
        filled = 0
        for external_id, (from_type, to_type) in types_by_external_id.items():
            if to_type is None:
                continue
            from_value = from_type.value if from_type is not None else None
            fillable = or_(_TO_UNTYPED, _FROM_UNTYPED) if from_value else _TO_UNTYPED
            result = await self._session.execute(
                update(EventModel)
                .where(EventModel.external_id == external_id, fillable)
                .values(
                    # COALESCE: fill only the empty side, never change a value.
                    from_state_type=func.coalesce(EventModel.from_state_type, from_value),
                    to_state_type=func.coalesce(EventModel.to_state_type, to_type.value),
                )
            )
            filled += cast(CursorResult[Any], result).rowcount
        return filled
