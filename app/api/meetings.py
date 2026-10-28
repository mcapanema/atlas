from datetime import date

from fastapi import APIRouter, Query, status

from app.api.advice_runner import AdviceRunnerDep
from app.api.deps import AdviceRunServiceDep, AdvisorPortDep
from app.api.schemas import MeetingPrepRunRead
from app.api.scope import ScopeDep
from app.domain.advisor.entities import MeetingType, meeting_persona
from app.domain.advisor.runs import run_params

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


@router.post("/prep", response_model=MeetingPrepRunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_meeting_prep(
    runner: AdviceRunnerDep,
    # Declared before ScopeDep on purpose: FastAPI solves dependencies in
    # signature order, so an unconfigured advisor answers 409 even when the
    # scope is also unknown (same pattern as /api/recommendations).
    advisor: AdvisorPortDep,
    scope: ScopeDep,
    meeting: MeetingType,
    window_days: int | None = Query(default=None, ge=7, le=365),
    remaining: int | None = Query(default=None, ge=0),
    target_date: date | None = None,
) -> MeetingPrepRunRead:
    """Start generating meeting prep in the background (the stand-alone
    sibling of the MCP daily_standup/retrospective/planning prompts), or
    join the live run for the same request; read it with `GET`.
    Without `window_days`, a retrospective covers the team's sprint length.
    `remaining`/`target_date` are the planning what-ifs."""
    run = await runner.start_meeting_prep(
        advisor,
        team_id=scope.team_id,
        project_id=scope.project_id,
        meeting=meeting,
        window_days=window_days,
        remaining=remaining,
        target_date=target_date,
    )
    return MeetingPrepRunRead.from_run(run)


@router.get("/prep", response_model=MeetingPrepRunRead | None)
async def get_meeting_prep(
    runs: AdviceRunServiceDep,
    scope: ScopeDep,
    meeting: MeetingType,
    window_days: int | None = Query(default=None, ge=7, le=365),
    remaining: int | None = Query(default=None, ge=0),
    target_date: date | None = None,
) -> MeetingPrepRunRead | None:
    """The latest stored prep for this exact request, or null."""
    run = await runs.latest(
        team_id=scope.team_id,
        project_id=scope.project_id,
        persona=meeting_persona(meeting),
        params=run_params(window_days=window_days, remaining=remaining, target_date=target_date),
    )
    return MeetingPrepRunRead.from_run(run) if run else None
