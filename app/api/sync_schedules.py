from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import SyncScheduleServiceDep
from app.api.schemas import SyncRunRead, SyncScheduleRead, SyncScheduleWrite
from app.application.sync.service import UnknownOrganizationError
from app.application.sync_schedules.service import ScheduleSettings, SyncScheduleView

# Nested under the organization it schedules: /api/organizations/{id}/sync-schedule.
router = APIRouter(prefix="/api/organizations", tags=["sync-schedules"])


def _read(view: SyncScheduleView) -> SyncScheduleRead:
    schedule = view.schedule
    last_run = schedule.last_run
    return SyncScheduleRead(
        enabled=schedule.enabled,
        days=sorted(schedule.days),
        window_start=schedule.window_start,
        window_end=schedule.window_end,
        interval_minutes=schedule.interval_minutes,
        timezone=schedule.timezone,
        updated_at=schedule.updated_at,
        last_run=SyncRunRead.model_validate(last_run) if last_run is not None else None,
        last_manual_sync_at=schedule.last_manual_sync_at,
        next_run_at=view.next_run_at,
    )


def _not_found(exc: UnknownOrganizationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{organization_id}/sync-schedule", response_model=SyncScheduleRead | None)
async def get_sync_schedule(
    organization_id: UUID, service: SyncScheduleServiceDep
) -> SyncScheduleRead | None:
    try:
        view = await service.get(organization_id)
    except UnknownOrganizationError as exc:
        raise _not_found(exc) from exc
    return _read(view) if view is not None else None


@router.put("/{organization_id}/sync-schedule", response_model=SyncScheduleRead)
async def put_sync_schedule(
    organization_id: UUID, payload: SyncScheduleWrite, service: SyncScheduleServiceDep
) -> SyncScheduleRead:
    settings = ScheduleSettings(
        enabled=payload.enabled,
        days=frozenset(payload.days),
        window_start=payload.window_start,
        window_end=payload.window_end,
        interval_minutes=payload.interval_minutes,
        timezone=payload.timezone,
    )
    try:
        view = await service.save(organization_id, settings)
    except UnknownOrganizationError as exc:
        raise _not_found(exc) from exc
    return _read(view)
