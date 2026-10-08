import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.auto_sync import AutoSyncRunnerDep
from app.api.deps import (
    MetricRulesServiceDep,
    SessionDep,
    SnapshotServiceDep,
    SyncScheduleServiceDep,
    SyncServiceDep,
)
from app.api.recompute import RecomputeRunnerDep
from app.api.schemas import LinearStatusRead, SyncRequest, SyncSummaryRead
from app.application.snapshots.service import SnapshotService
from app.application.sync.service import (
    SyncService,
    SyncSummary,
    UnknownOrganizationError,
    UnknownTeamError,
)
from app.application.sync_schedules.service import SyncScheduleService
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("/linear", response_model=LinearStatusRead)
async def linear_status(auto_sync: AutoSyncRunnerDep) -> LinearStatusRead:
    return LinearStatusRead(
        configured=bool(get_settings().linear_api_key), auto_syncing=auto_sync.auto_syncing
    )


async def _run_sync(
    service: SyncService, organization_id: UUID | None, *, rebuild: bool
) -> SyncSummary:
    try:
        return await service.sync(organization_id, rebuild=rebuild)
    except UnknownOrganizationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


async def _after_sync(
    snapshots: SnapshotService, schedules: SyncScheduleService, summary: SyncSummary
) -> None:
    # Same request-scoped transaction as the sync itself: the synced data,
    # its day's snapshots and the schedule's manual-sync mark land together.
    captured = await snapshots.capture_all()
    logger.info("Captured snapshots for %d scope(s) post-sync", captured)
    # Skips a scheduled slot this sync made redundant (ADR-0014).
    await schedules.record_manual_sync(summary.organization_id)


# ponytail: synchronous blocking sync — fine for thousands of issues on
# local SQLite; move to a background job + progress reporting if a
# workspace ever makes one request too slow.
@router.post("/linear/sync", response_model=SyncSummaryRead)
async def sync_linear(
    payload: SyncRequest,
    service: SyncServiceDep,
    snapshots: SnapshotServiceDep,
    rules: MetricRulesServiceDep,
    session: SessionDep,
    runner: RecomputeRunnerDep,
    auto_sync: AutoSyncRunnerDep,
    schedules: SyncScheduleServiceDep,
) -> SyncSummaryRead:
    # One sync at a time (ADR-0014): a scheduled tick skips while this holds
    # the lock, and the commit lands inside it, so the next sync starts
    # from this one's writes.
    async with auto_sync.lock:
        if not payload.rebuild:
            summary = await _run_sync(service, payload.organization_id, rebuild=False)
            await _after_sync(snapshots, schedules, summary)
            await session.commit()
            return SyncSummaryRead.model_validate(summary)
        # A rebuild rewrites stored events, so snapshot history computed from the
        # old ones is rewritten too (ADR-0013). Paused before any write: a running
        # scope rewrite holds SQLite's write lock (see metric_rules._save).
        async with runner.paused() as queue:
            summary = await _run_sync(service, payload.organization_id, rebuild=True)
            await _after_sync(snapshots, schedules, summary)
            scopes = await rules.organization_scopes(summary.organization_id)
            await rules.start_recompute(summary.organization_id)
            await session.commit()
            queue(summary.organization_id, scopes)
    return SyncSummaryRead.model_validate(summary)


@router.post("/linear/teams/{team_id}/sync", response_model=SyncSummaryRead)
async def sync_linear_team(
    team_id: UUID,
    service: SyncServiceDep,
    snapshots: SnapshotServiceDep,
    session: SessionDep,
    auto_sync: AutoSyncRunnerDep,
) -> SyncSummaryRead:
    # Same lock as every sync (ADR-0014). One team's sync leaves the others
    # stale, so it's not recorded on the schedule (a due slot still runs)
    # and only this team's scopes are snapshotted.
    async with auto_sync.lock:
        try:
            summary = await service.sync_team(team_id)
        except UnknownTeamError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        captured = await snapshots.capture_team(team_id)
        logger.info("Captured snapshots for %d scope(s) post-team-sync", captured)
        await session.commit()
    return SyncSummaryRead.model_validate(summary)
