from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CodebaseServiceDep
from app.api.schemas import CodebaseRead, CodebaseWrite
from app.application.codebases.service import UnknownCodebaseError

router = APIRouter(prefix="/api/codebases", tags=["codebases"])


@router.get("", response_model=list[CodebaseRead])
async def list_codebases(organization_id: UUID, service: CodebaseServiceDep) -> list[CodebaseRead]:
    return [CodebaseRead.of(overview) for overview in await service.list(organization_id)]


# PUT, not PATCH: the body replaces the codebase's whole editable state.
@router.put("/{codebase_id}", response_model=CodebaseRead)
async def update_codebase(
    codebase_id: UUID, payload: CodebaseWrite, service: CodebaseServiceDep
) -> CodebaseRead:
    try:
        updated = await service.update(
            codebase_id,
            team_id=payload.team_id,
            production_environment=payload.production_environment,
        )
    except UnknownCodebaseError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # The list carries the stored counts; one organization's codebases are few.
    overviews = await service.list(updated.organization_id)
    return next(CodebaseRead.of(o) for o in overviews if o.codebase.id == codebase_id)
