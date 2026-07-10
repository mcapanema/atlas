"""Scope resolution shared by the analytics endpoints (metrics/forecasts/advisor).

Exactly one of team_id/project_id must be provided (422), and it must exist
(404) — an unknown scope must not fabricate empty analytics or trigger a paid
LLM call.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.api.deps import ProjectServiceDep, TeamServiceDep


@dataclass(frozen=True)
class Scope:
    team_id: UUID | None
    project_id: UUID | None


async def get_scope(
    teams: TeamServiceDep,
    projects: ProjectServiceDep,
    team_id: UUID | None = None,
    project_id: UUID | None = None,
) -> Scope:
    if (team_id is None) == (project_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide exactly one of team_id or project_id",
        )
    if team_id is not None and await teams.get_team(team_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Team {team_id} not found"
        )
    if project_id is not None and await projects.get_project(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )
    return Scope(team_id=team_id, project_id=project_id)


ScopeDep = Annotated[Scope, Depends(get_scope)]
