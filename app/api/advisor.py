from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import AdvisorServiceDep
from app.api.metrics import _require_exactly_one_scope
from app.api.schemas import AdvisorStatusRead, DeliveryAdviceRead
from app.config import get_settings

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/status", response_model=AdvisorStatusRead)
async def advisor_status() -> AdvisorStatusRead:
    return AdvisorStatusRead(configured=bool(get_settings().openrouter_api_key))


# ponytail: synchronous LLM call on GET (tens of seconds) — fine for one EM
# clicking a button; move to a background job + stored result if advice ever
# needs to be scheduled or shared.
@router.get("", response_model=DeliveryAdviceRead)
async def get_recommendations(
    service: AdvisorServiceDep,
    team_id: UUID | None = None,
    project_id: UUID | None = None,
    window_days: int = Query(default=30, ge=7, le=365),
) -> DeliveryAdviceRead:
    _require_exactly_one_scope(team_id, project_id)
    advice = await service.get_advice(
        team_id=team_id, project_id=project_id, window_days=window_days
    )
    return DeliveryAdviceRead.model_validate(advice)
