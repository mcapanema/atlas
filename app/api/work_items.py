from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import WorkItemServiceDep
from app.api.schemas import WorkItemCreate, WorkItemRead

router = APIRouter(prefix="/api/work-items", tags=["work-items"])


@router.get("", response_model=list[WorkItemRead])
async def list_work_items(
    service: WorkItemServiceDep,
    team_id: UUID | None = None,
    project_id: UUID | None = None,
) -> list[WorkItemRead]:
    items = await service.list_work_items(team_id=team_id, project_id=project_id)
    return [WorkItemRead.model_validate(item) for item in items]


@router.post("", response_model=WorkItemRead, status_code=status.HTTP_201_CREATED)
async def create_work_item(
    payload: WorkItemCreate, service: WorkItemServiceDep
) -> WorkItemRead:
    item = await service.create_work_item(
        team_id=payload.team_id,
        title=payload.title,
        type=payload.type,
        state=payload.state,
        project_id=payload.project_id,
        external_id=payload.external_id,
    )
    return WorkItemRead.model_validate(item)
