from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ProjectServiceDep, TeamServiceDep
from app.api.schemas import ProjectCreate, ProjectRead
from app.domain.projects.entities import Project

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _read(project: Project, team_ids: list[UUID]) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        team_id=project.team_id,
        team_ids=team_ids,
        name=project.name,
        external_id=project.external_id,
        created_at=project.created_at,
    )


@router.get("", response_model=list[ProjectRead])
async def list_projects(service: ProjectServiceDep) -> list[ProjectRead]:
    return [
        _read(project, team_ids) for project, team_ids in await service.list_projects_with_teams()
    ]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, service: ProjectServiceDep, teams: TeamServiceDep
) -> ProjectRead:
    if await teams.get_team(payload.team_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    project = await service.create_project(
        team_id=payload.team_id, name=payload.name, external_id=payload.external_id
    )
    return _read(project, [project.team_id])
