from fastapi import APIRouter, status

from app.api.deps import ProjectServiceDep
from app.api.schemas import ProjectCreate, ProjectRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
async def list_projects(service: ProjectServiceDep) -> list[ProjectRead]:
    projects = await service.list_projects()
    return [ProjectRead.model_validate(project) for project in projects]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, service: ProjectServiceDep) -> ProjectRead:
    project = await service.create_project(
        team_id=payload.team_id, name=payload.name, external_id=payload.external_id
    )
    return ProjectRead.model_validate(project)
