from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DeliveryDataSourceDep, SessionDep, SyncServiceDep
from app.api.schemas import LinearStatusRead, SyncJobRead, SyncRequest
from app.api.sync_jobs import SyncBusyError, SyncJobRequest, SyncJobRunner, SyncJobRunnerDep
from app.application.sync.service import UnknownOrganizationError, UnknownTeamError
from app.config import get_settings
from app.domain.sync.port import DeliveryDataSource

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("/linear", response_model=LinearStatusRead)
async def linear_status(jobs: SyncJobRunnerDep) -> LinearStatusRead:
    running = jobs.running
    return LinearStatusRead(
        configured=bool(get_settings().linear_api_key),
        running=SyncJobRead.of(running) if running is not None else None,
    )


def _start(jobs: SyncJobRunner, request: SyncJobRequest, source: DeliveryDataSource) -> SyncJobRead:
    try:
        return SyncJobRead.of(jobs.start(request, source))
    except SyncBusyError as exc:
        running = exc.job
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Another {running.request.kind} sync is running "
                f"(started {running.started_at:%H:%M} UTC); try again when it finishes"
            ),
        ) from exc


# The sync runs as a background job (sync_jobs.py); 404 / 422 / 409 still
# answer synchronously, then the client polls GET /linear/jobs/{job_id}.
@router.post("/linear/sync", response_model=SyncJobRead, status_code=status.HTTP_202_ACCEPTED)
async def sync_linear(
    payload: SyncRequest,
    service: SyncServiceDep,
    source: DeliveryDataSourceDep,
    session: SessionDep,
    jobs: SyncJobRunnerDep,
) -> SyncJobRead:
    try:
        organization_id = await service.resolve_organization(payload.organization_id)
    except UnknownOrganizationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # Before the job starts: an organization bootstrapped above must be
    # visible to the job's own session.
    await session.commit()
    request = SyncJobRequest(organization_id, "organization", "manual", rebuild=payload.rebuild)
    return _start(jobs, request, source)


@router.post(
    "/linear/teams/{team_id}/sync",
    response_model=SyncJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_linear_team(
    team_id: UUID,
    service: SyncServiceDep,
    source: DeliveryDataSourceDep,
    session: SessionDep,
    jobs: SyncJobRunnerDep,
) -> SyncJobRead:
    try:
        organization_id = await service.resolve_team(team_id)
    except UnknownTeamError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # Ends the request's read transaction before the job writes.
    await session.commit()
    request = SyncJobRequest(organization_id, "team", "manual", team_id=team_id)
    return _start(jobs, request, source)


@router.get("/linear/jobs/{job_id}", response_model=SyncJobRead)
async def linear_sync_job(job_id: UUID, jobs: SyncJobRunnerDep) -> SyncJobRead:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync job not found; Atlas may have restarted before it finished",
        )
    return SyncJobRead.of(job)
