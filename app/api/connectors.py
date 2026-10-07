import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import MetricRulesServiceDep, SessionDep, SnapshotServiceDep, SyncServiceDep
from app.api.recompute import RecomputeRunnerDep
from app.api.schemas import IntegrationStatusRead, SyncRequest, SyncSummaryRead
from app.application.snapshots.service import SnapshotService
from app.application.sync.service import SyncService, SyncSummary, UnknownOrganizationError
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("/linear", response_model=IntegrationStatusRead)
async def linear_status() -> IntegrationStatusRead:
    return IntegrationStatusRead(configured=bool(get_settings().linear_api_key))


async def _run_sync(
    service: SyncService, organization_id: UUID | None, *, rebuild: bool
) -> SyncSummary:
    try:
        return await service.sync(organization_id, rebuild=rebuild)
    except UnknownOrganizationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


async def _capture(snapshots: SnapshotService) -> None:
    # Same request-scoped transaction as the sync itself: the synced data
    # and its day's snapshots land together or not at all.
    captured = await snapshots.capture_all()
    logger.info("Captured snapshots for %d scope(s) post-sync", captured)


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
) -> SyncSummaryRead:
    if not payload.rebuild:
        summary = await _run_sync(service, payload.organization_id, rebuild=False)
        await _capture(snapshots)
        return SyncSummaryRead.model_validate(summary)
    # A rebuild rewrites stored events, so snapshot history computed from the
    # old ones is rewritten too (ADR-0013). Paused before any write: a running
    # scope rewrite holds SQLite's write lock (see metric_rules._save).
    async with runner.paused() as queue:
        summary = await _run_sync(service, payload.organization_id, rebuild=True)
        await _capture(snapshots)
        scopes = await rules.organization_scopes(summary.organization_id)
        await rules.start_recompute(summary.organization_id)
        await session.commit()
        queue(summary.organization_id, scopes)
    return SyncSummaryRead.model_validate(summary)
