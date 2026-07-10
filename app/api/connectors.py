from fastapi import APIRouter

from app.api.deps import SyncServiceDep
from app.api.schemas import ConnectorStatusRead, SyncRequest, SyncSummaryRead
from app.config import get_settings

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("/linear", response_model=ConnectorStatusRead)
async def linear_status() -> ConnectorStatusRead:
    return ConnectorStatusRead(configured=bool(get_settings().linear_api_key))


# ponytail: synchronous blocking sync — fine for thousands of issues on
# local SQLite; move to a background job + progress reporting if a
# workspace ever makes one request too slow.
@router.post("/linear/sync", response_model=SyncSummaryRead)
async def sync_linear(payload: SyncRequest, service: SyncServiceDep) -> SyncSummaryRead:
    summary = await service.sync(payload.organization_id)
    return SyncSummaryRead.model_validate(summary)
