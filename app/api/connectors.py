from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import (
    CodeHostSourceDep,
    CredentialServiceDep,
    DeliveryDataSourceDep,
    SessionDep,
    SyncServiceDep,
    code_sync_service_for,
)
from app.api.schemas import (
    DEFAULT_ADVISOR_MODEL,
    CodeSyncRequest,
    DatadogCredentialsWrite,
    DatadogStatusRead,
    GitHubCredentialsWrite,
    GitHubStatusRead,
    LinearCredentialsWrite,
    LinearStatusRead,
    OpenRouterCredentialsWrite,
    OpenRouterStatusRead,
    SyncJobRead,
    SyncRequest,
)
from app.api.sync_jobs import (
    SyncBusyError,
    SyncJob,
    SyncJobRequest,
    SyncJobRunner,
    SyncJobRunnerDep,
    kind_label,
)
from app.application.credentials.service import CredentialService
from app.application.sync.service import UnknownOrganizationError, UnknownTeamError
from app.domain.credentials.entities import Credential, Integration

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


def _running(jobs: SyncJobRunner) -> SyncJobRead | None:
    running = jobs.running
    return SyncJobRead.of(running) if running is not None else None


async def _linear_status(service: CredentialService, jobs: SyncJobRunner) -> LinearStatusRead:
    stored = await service.get(Integration.LINEAR)
    return LinearStatusRead(
        configured=stored is not None,
        hint=stored.hint if stored else None,
        running=_running(jobs),
    )


async def _github_status(service: CredentialService, jobs: SyncJobRunner) -> GitHubStatusRead:
    stored = await service.get(Integration.GITHUB)
    return GitHubStatusRead(
        configured=stored is not None,
        owner=stored.owner if stored else None,
        hint=stored.hint if stored else None,
        running=_running(jobs),
    )


async def _datadog_status(service: CredentialService, jobs: SyncJobRunner) -> DatadogStatusRead:
    stored = await service.get(Integration.DATADOG)
    return DatadogStatusRead(
        configured=stored is not None,
        site=stored.site if stored else None,
        hint=stored.hint if stored else None,
        running=_running(jobs),
    )


async def _openrouter_status(service: CredentialService) -> OpenRouterStatusRead:
    stored = await service.get(Integration.OPENROUTER)
    return OpenRouterStatusRead(
        configured=stored is not None,
        model=(stored.model if stored else None) or DEFAULT_ADVISOR_MODEL,
        hint=stored.hint if stored else None,
    )


@router.get("/linear", response_model=LinearStatusRead)
async def linear_status(jobs: SyncJobRunnerDep, service: CredentialServiceDep) -> LinearStatusRead:
    return await _linear_status(service, jobs)


# Every credentials PUT: a rejected key (CredentialCheckError) answers 422 and an unreachable
# provider 502 through create_app()'s handlers; nothing is stored either way.
@router.put("/linear/credentials", response_model=LinearStatusRead)
async def put_linear_credentials(
    payload: LinearCredentialsWrite, jobs: SyncJobRunnerDep, service: CredentialServiceDep
) -> LinearStatusRead:
    await service.save(Credential(Integration.LINEAR, payload.api_key))
    return await _linear_status(service, jobs)


@router.delete("/linear/credentials", response_model=LinearStatusRead)
async def delete_linear_credentials(
    jobs: SyncJobRunnerDep, service: CredentialServiceDep
) -> LinearStatusRead:
    await service.remove(Integration.LINEAR)
    return await _linear_status(service, jobs)


@router.get("/openrouter", response_model=OpenRouterStatusRead)
async def openrouter_status(service: CredentialServiceDep) -> OpenRouterStatusRead:
    return await _openrouter_status(service)


# An omitted key keeps the stored one; it is checked again with the new model.
@router.put("/openrouter/credentials", response_model=OpenRouterStatusRead)
async def put_openrouter_credentials(
    payload: OpenRouterCredentialsWrite, service: CredentialServiceDep
) -> OpenRouterStatusRead:
    await service.update(Integration.OPENROUTER, payload.api_key, model=payload.model)
    return await _openrouter_status(service)


@router.delete("/openrouter/credentials", response_model=OpenRouterStatusRead)
async def delete_openrouter_credentials(service: CredentialServiceDep) -> OpenRouterStatusRead:
    await service.remove(Integration.OPENROUTER)
    return await _openrouter_status(service)


def _start(start: Callable[[], SyncJob]) -> SyncJobRead:
    """Run a runner `start*` call; a busy runner answers 409."""
    try:
        return SyncJobRead.of(start())
    except SyncBusyError as exc:
        running = exc.job
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Another {kind_label(running.request.kind)} sync is running "
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
    return _start(lambda: jobs.start(request, source))


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
    return _start(lambda: jobs.start(request, source))


def _job(jobs: SyncJobRunner, job_id: UUID) -> SyncJobRead:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync job not found; Atlas may have restarted before it finished",
        )
    return SyncJobRead.of(job)


@router.get("/linear/jobs/{job_id}", response_model=SyncJobRead)
async def linear_sync_job(job_id: UUID, jobs: SyncJobRunnerDep) -> SyncJobRead:
    return _job(jobs, job_id)


@router.get("/github", response_model=GitHubStatusRead)
async def github_status(jobs: SyncJobRunnerDep, service: CredentialServiceDep) -> GitHubStatusRead:
    return await _github_status(service, jobs)


# An omitted token keeps the stored one; it is checked again against the new owner.
@router.put("/github/credentials", response_model=GitHubStatusRead)
async def put_github_credentials(
    payload: GitHubCredentialsWrite, jobs: SyncJobRunnerDep, service: CredentialServiceDep
) -> GitHubStatusRead:
    await service.update(Integration.GITHUB, payload.token, owner=payload.owner)
    return await _github_status(service, jobs)


@router.delete("/github/credentials", response_model=GitHubStatusRead)
async def delete_github_credentials(
    jobs: SyncJobRunnerDep, service: CredentialServiceDep
) -> GitHubStatusRead:
    await service.remove(Integration.GITHUB)
    return await _github_status(service, jobs)


@router.get("/datadog", response_model=DatadogStatusRead)
async def datadog_status(
    jobs: SyncJobRunnerDep, service: CredentialServiceDep
) -> DatadogStatusRead:
    return await _datadog_status(service, jobs)


@router.put("/datadog/credentials", response_model=DatadogStatusRead)
async def put_datadog_credentials(
    payload: DatadogCredentialsWrite, jobs: SyncJobRunnerDep, service: CredentialServiceDep
) -> DatadogStatusRead:
    await service.save(
        Credential(
            Integration.DATADOG,
            payload.api_key,
            application_key=payload.application_key,
            site=payload.site,
        )
    )
    return await _datadog_status(service, jobs)


@router.delete("/datadog/credentials", response_model=DatadogStatusRead)
async def delete_datadog_credentials(
    jobs: SyncJobRunnerDep, service: CredentialServiceDep
) -> DatadogStatusRead:
    await service.remove(Integration.DATADOG)
    return await _datadog_status(service, jobs)


# Same job model as the Linear sync: 202 now, then poll GET /github/jobs/{job_id}.
@router.post("/github/sync", response_model=SyncJobRead, status_code=status.HTTP_202_ACCEPTED)
async def sync_github(
    payload: CodeSyncRequest,
    source: CodeHostSourceDep,
    session: SessionDep,
    jobs: SyncJobRunnerDep,
) -> SyncJobRead:
    service = code_sync_service_for(session, source)
    try:
        organization_id = await service.resolve_organization(payload.organization_id)
    except UnknownOrganizationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # Ends the request's read transaction before the job writes.
    await session.commit()
    request = SyncJobRequest(organization_id, "code", "manual")
    return _start(lambda: jobs.start_code(request, source))


@router.get("/github/jobs/{job_id}", response_model=SyncJobRead)
async def github_sync_job(job_id: UUID, jobs: SyncJobRunnerDep) -> SyncJobRead:
    return _job(jobs, job_id)
