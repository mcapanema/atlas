from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import EventServiceDep
from app.api.schemas import EventCreate, EventRead

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[EventRead])
async def list_events(service: EventServiceDep, work_item_id: UUID) -> list[EventRead]:
    events = await service.list_for_work_item(work_item_id)
    return [EventRead.model_validate(event) for event in events]


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def record_event(payload: EventCreate, service: EventServiceDep) -> EventRead:
    event = await service.record_event(
        work_item_id=payload.work_item_id,
        type=payload.type,
        occurred_at=payload.occurred_at,
        from_state=payload.from_state,
        to_state=payload.to_state,
        external_id=payload.external_id,
    )
    return EventRead.model_validate(event)
