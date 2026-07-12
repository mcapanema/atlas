import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import SnapshotServiceDep, SyncServiceDep
from app.api.schemas import IntegrationStatusRead, SyncRequest, SyncSummaryRead
from app.application.sync.service import UnknownOrganizationError
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("/linear", response_model=IntegrationStatusRead)
async def linear_status() -> IntegrationStatusRead:
    return IntegrationStatusRead(configured=bool(get_settings().linear_api_key))


# ponytail: synchronous blocking sync — fine for thousands of issues on
# local SQLite; move to a background job + progress reporting if a
# workspace ever makes one request too slow.
@router.post("/linear/sync", response_model=SyncSummaryRead)
async def sync_linear(
    payload: SyncRequest, service: SyncServiceDep, snapshots: SnapshotServiceDep
) -> SyncSummaryRead:
    try:
        summary = await service.sync(payload.organization_id)
    except UnknownOrganizationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # Same request-scoped transaction as the sync itself: the synced data
    # and its day's snapshots land together or not at all.
    captured = await snapshots.capture_all()
    logger.info("Captured snapshots for %d scope(s) post-sync", captured)
    return SyncSummaryRead.model_validate(summary)
