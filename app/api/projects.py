from fastapi import APIRouter, HTTPException, status

from app.api.deps import ProjectServiceDep, TeamServiceDep
from app.api.schemas import ProjectCreate, ProjectRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
async def list_projects(service: ProjectServiceDep) -> list[ProjectRead]:
    projects = await service.list_projects()
    return [ProjectRead.model_validate(project) for project in projects]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, service: ProjectServiceDep, teams: TeamServiceDep
) -> ProjectRead:
    if await teams.get_team(payload.team_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    project = await service.create_project(
        team_id=payload.team_id, name=payload.name, external_id=payload.external_id
    )
    return ProjectRead.model_validate(project)
