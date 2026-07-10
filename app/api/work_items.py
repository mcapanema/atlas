from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import (
    EventServiceDep,
    ProjectServiceDep,
    TeamServiceDep,
    WorkItemServiceDep,
)
from app.api.schemas import WorkItemCreate, WorkItemRead, WorkItemTimelineRead

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
    payload: WorkItemCreate,
    service: WorkItemServiceDep,
    teams: TeamServiceDep,
    projects: ProjectServiceDep,
) -> WorkItemRead:
    if await teams.get_team(payload.team_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    if payload.project_id is not None and await projects.get_project(payload.project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    item = await service.create_work_item(
        team_id=payload.team_id,
        title=payload.title,
        type=payload.type,
        state=payload.state,
        project_id=payload.project_id,
        external_id=payload.external_id,
    )
    return WorkItemRead.model_validate(item)


@router.get("/{work_item_id}", response_model=WorkItemRead)
async def get_work_item(work_item_id: UUID, service: WorkItemServiceDep) -> WorkItemRead:
    item = await service.get_work_item(work_item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found")
    return WorkItemRead.model_validate(item)


@router.get("/{work_item_id}/timeline", response_model=WorkItemTimelineRead)
async def get_work_item_timeline(
    work_item_id: UUID,
    work_items: WorkItemServiceDep,
    events: EventServiceDep,
) -> WorkItemTimelineRead:
    if await work_items.get_work_item(work_item_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found")
    return WorkItemTimelineRead.model_validate(await events.get_timeline(work_item_id))
