from fastapi import APIRouter, Query

from app.api.deps import AdvisorPortDep, AdvisorServiceDep, SessionDep
from app.api.schemas import DeliveryAdviceRead, IntegrationStatusRead
from app.api.scope import ScopeDep
from app.config import get_settings

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/status", response_model=IntegrationStatusRead)
async def advisor_status() -> IntegrationStatusRead:
    return IntegrationStatusRead(configured=bool(get_settings().openrouter_api_key))


# ponytail: synchronous LLM call on GET (tens of seconds) — fine for one EM
# clicking a button; move to a background job + stored result if advice ever
# needs to be scheduled or shared.
@router.get("", response_model=DeliveryAdviceRead)
async def get_recommendations(
    service: AdvisorServiceDep,
    # Declared before ScopeDep on purpose: FastAPI solves dependencies in
    # signature order, so an unconfigured advisor answers 409 even when the
    # scope is also unknown.
    advisor: AdvisorPortDep,
    session: SessionDep,
    scope: ScopeDep,
    window_days: int = Query(default=30, ge=7, le=365),
) -> DeliveryAdviceRead:
    context = await service.build_context(
        team_id=scope.team_id, project_id=scope.project_id, window_days=window_days
    )
    # Release the read transaction before the LLM call — holding it open
    # would block every SQLite writer for up to 120 seconds.
    await session.commit()
    advice = await advisor.advise(context)
    return DeliveryAdviceRead.model_validate(advice)
