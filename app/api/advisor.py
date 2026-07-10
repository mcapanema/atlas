from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import AdvisorPortDep, AdvisorServiceDep, SessionDep
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
    advisor: AdvisorPortDep,
    session: SessionDep,
    team_id: UUID | None = None,
    project_id: UUID | None = None,
    window_days: int = Query(default=30, ge=7, le=365),
) -> DeliveryAdviceRead:
    _require_exactly_one_scope(team_id, project_id)
    context = await service.build_context(
        team_id=team_id, project_id=project_id, window_days=window_days
    )
    # Release the read transaction before the LLM call — holding it open
    # would block every SQLite writer for up to 120 seconds.
    await session.commit()
    advice = await advisor.advise(context)
    return DeliveryAdviceRead.model_validate(advice)
