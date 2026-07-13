from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import AdvisorPortDep, AdvisorServiceDep, PersonaServiceDep, SessionDep
from app.api.schemas import MeetingPrepRead
from app.api.scope import ScopeDep
from app.domain.advisor.entities import MeetingType, meeting_persona

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


# ponytail: synchronous LLM call on GET, same trade as /api/recommendations —
# move to a background job + stored result if preps ever need to be scheduled.
@router.get("/prep", response_model=MeetingPrepRead)
async def get_meeting_prep(
    service: AdvisorServiceDep,
    # Declared before ScopeDep on purpose: FastAPI solves dependencies in
    # signature order, so an unconfigured advisor answers 409 even when the
    # scope is also unknown (same pattern as /api/recommendations).
    advisor: AdvisorPortDep,
    session: SessionDep,
    personas: PersonaServiceDep,
    scope: ScopeDep,
    meeting: MeetingType,
    window_days: int = Query(default=30, ge=7, le=365),
    remaining: int | None = Query(default=None, ge=0),
    target_date: date | None = None,
) -> MeetingPrepRead:
    """Generate meeting prep with the internal advisor (the stand-alone
    sibling of the MCP daily_standup/retrospective/planning prompts).
    `remaining`/`target_date` are the planning what-ifs."""
    context = await service.build_meeting_context(
        team_id=scope.team_id,
        project_id=scope.project_id,
        window_days=window_days,
        remaining=remaining,
        target_date=target_date,
    )
    active = await personas.active_guidance(meeting_persona(meeting))
    # Release the read transaction before the LLM call — holding it open
    # would block every SQLite writer for up to 120 seconds.
    await session.commit()
    prep = await advisor.prepare_meeting(
        context, meeting=meeting, guidance=active.guidance if active else None
    )
    return MeetingPrepRead.model_validate(prep)
