from datetime import datetime
from uuid import UUID

from app.domain.events.entities import Event, EventType
from app.domain.events.repository import EventRepository
from app.domain.events.timeline import WorkItemTimeline, derive_timeline


class EventService:
    """Application use cases for Events."""

    def __init__(self, repository: EventRepository) -> None:
        self._repository = repository

    async def record_event(
        self,
        work_item_id: UUID,
        type: EventType,
        occurred_at: datetime,
        from_state: str | None = None,
        to_state: str | None = None,
        external_id: str | None = None,
    ) -> Event:
        event = Event(
            work_item_id=work_item_id,
            type=type,
            occurred_at=occurred_at,
            from_state=from_state,
            to_state=to_state,
            external_id=external_id,
        )
        await self._repository.add(event)
        return event

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]:
        return await self._repository.list_for_work_item(work_item_id)

    async def get_timeline(self, work_item_id: UUID) -> WorkItemTimeline:
        events = await self._repository.list_for_work_item(work_item_id)
        return derive_timeline(events)
