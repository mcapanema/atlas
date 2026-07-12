from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdvisorPortDep, PersonaServiceDep, SessionDep
from app.api.schemas import AdviceFeedbackCreate, AdviceFeedbackRead, PersonaGuidanceRead
from app.domain.advisor.entities import Persona

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.post("/{persona}/feedback", response_model=AdviceFeedbackRead, status_code=201)
async def submit_feedback(
    persona: Persona, payload: AdviceFeedbackCreate, service: PersonaServiceDep
) -> AdviceFeedbackRead:
    feedback = await service.record_feedback(
        persona=persona,
        rating=payload.rating,
        comment=payload.comment,
        advice_summary=payload.advice_summary,
    )
    return AdviceFeedbackRead.model_validate(feedback)


@router.get("/{persona}/guidance", response_model=list[PersonaGuidanceRead])
async def list_guidance(
    persona: Persona, service: PersonaServiceDep
) -> list[PersonaGuidanceRead]:
    versions = await service.list_guidance(persona)
    return [PersonaGuidanceRead.model_validate(g) for g in versions]


@router.post("/{persona}/reflect", response_model=PersonaGuidanceRead, status_code=201)
async def reflect(
    persona: Persona,
    # Declared before the service on purpose: an unconfigured advisor answers
    # 409 before any feedback/guidance state is consulted (same pattern as
    # GET /api/recommendations).
    advisor: AdvisorPortDep,
    service: PersonaServiceDep,
    session: SessionDep,
) -> PersonaGuidanceRead:
    pending = await service.pending_feedback(persona)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No new feedback to reflect on; rate some advice first",
        )
    current = await service.active_guidance(persona)
    # Release the read transaction before the LLM call — holding it open
    # would block every SQLite writer for up to 120 seconds. add_guidance
    # below runs in a fresh transaction committed by get_session.
    await session.commit()
    text = await advisor.reflect(
        persona=persona,
        feedback=pending,
        current_guidance=current.guidance if current else None,
    )
    guidance = await service.add_guidance(persona, text)
    return PersonaGuidanceRead.model_validate(guidance)


@router.post(
    "/{persona}/guidance/{version}/restore",
    response_model=PersonaGuidanceRead,
    status_code=201,
)
async def restore_guidance(
    persona: Persona, version: int, service: PersonaServiceDep
) -> PersonaGuidanceRead:
    guidance = await service.restore_guidance(persona, version)
    if guidance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown guidance version"
        )
    return PersonaGuidanceRead.model_validate(guidance)
