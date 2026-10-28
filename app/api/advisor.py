from fastapi import APIRouter, Query, status

from app.api.advice_runner import AdviceRunnerDep
from app.api.deps import AdviceRunServiceDep, AdvisorPortDep, AdvisorServiceDep
from app.api.schemas import AdviceContextRead, AdviceRunRead, IntegrationStatusRead
from app.api.scope import ScopeDep
from app.config import get_settings
from app.domain.advisor.entities import Persona
from app.domain.advisor.render import render_context
from app.domain.advisor.runs import run_params
from app.domain.metrics.windows import STATS_WINDOW_DAYS

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/status", response_model=IntegrationStatusRead)
async def advisor_status() -> IntegrationStatusRead:
    return IntegrationStatusRead(configured=bool(get_settings().openrouter_api_key))


@router.get("/context", response_model=AdviceContextRead)
async def get_advice_context(
    service: AdvisorServiceDep,
    scope: ScopeDep,
    window_days: int = Query(default=STATS_WINDOW_DAYS, ge=7, le=365),
) -> AdviceContextRead:
    """The advisor's input digest, for clients that bring their own LLM (MCP)."""
    context = await service.build_context(
        team_id=scope.team_id, project_id=scope.project_id, window_days=window_days
    )
    return AdviceContextRead(context=render_context(context))


@router.post("", response_model=AdviceRunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_recommendations(
    runner: AdviceRunnerDep,
    # Declared before ScopeDep on purpose: FastAPI solves dependencies in
    # signature order, so an unconfigured advisor answers 409 even when the
    # scope is also unknown.
    advisor: AdvisorPortDep,
    scope: ScopeDep,
    window_days: int = Query(default=STATS_WINDOW_DAYS, ge=7, le=365),
    # ponytail: no ge/le-style constraint needed, so a plain default (not
    # Query(default=...)) is enough — FastAPI still treats it as a query
    # param and 422s on an unrecognized value. Query() also works but ruff's
    # B008 check doesn't recognize Enum defaults as exempt like it does for
    # int/str/None.
    persona: Persona = Persona.AGILE_COACH,
) -> AdviceRunRead:
    """Start generating advice in the background (or join the live run for
    the same scope, persona and window); read it with `GET`."""
    run = await runner.start_advice(
        advisor,
        team_id=scope.team_id,
        project_id=scope.project_id,
        persona=persona,
        window_days=window_days,
    )
    return AdviceRunRead.from_run(run)


@router.get("", response_model=AdviceRunRead | None)
async def get_recommendations(
    runs: AdviceRunServiceDep,
    scope: ScopeDep,
    window_days: int = Query(default=STATS_WINDOW_DAYS, ge=7, le=365),
    persona: Persona = Persona.AGILE_COACH,
) -> AdviceRunRead | None:
    """The latest stored run for this scope, persona and window, or null."""
    run = await runs.latest(
        team_id=scope.team_id,
        project_id=scope.project_id,
        persona=persona,
        params=run_params(window_days=window_days),
    )
    return AdviceRunRead.from_run(run) if run else None
