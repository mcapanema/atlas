from fastapi import APIRouter, status

from app.api.deps import MetricRulesServiceDep, TeamServiceDep
from app.api.schemas import TeamCreate, TeamRead

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("", response_model=list[TeamRead])
async def list_teams(service: TeamServiceDep, rules: MetricRulesServiceDep) -> list[TeamRead]:
    teams = await service.list_teams()
    custom = await rules.custom_team_ids(teams)
    return [
        TeamRead.model_validate(team).model_copy(update={"has_custom_rules": team.id in custom})
        for team in teams
    ]


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(payload: TeamCreate, service: TeamServiceDep) -> TeamRead:
    team = await service.create_team(
        organization_id=payload.organization_id,
        name=payload.name,
        external_id=payload.external_id,
    )
    return TeamRead.model_validate(team)
