from fastapi import APIRouter, status

from app.api.deps import MetricRulesServiceDep, TeamServiceDep
from app.api.schemas import TeamCreate, TeamRead
from app.application.metric_rules.service import TeamRulesSummary
from app.domain.teams.entities import Team

router = APIRouter(prefix="/api/teams", tags=["teams"])


def _read(team: Team, rules: TeamRulesSummary) -> TeamRead:
    return TeamRead.model_validate(team).model_copy(
        update={
            "has_custom_rules": rules.custom,
            "sprint_length_days": rules.effective.sprint_length_days,
        }
    )


@router.get("", response_model=list[TeamRead])
async def list_teams(service: TeamServiceDep, rules: MetricRulesServiceDep) -> list[TeamRead]:
    teams = await service.list_teams()
    summaries = await rules.team_summaries(teams)
    return [_read(team, summaries[team.id]) for team in teams]


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate, service: TeamServiceDep, rules: MetricRulesServiceDep
) -> TeamRead:
    team = await service.create_team(
        organization_id=payload.organization_id,
        name=payload.name,
        external_id=payload.external_id,
    )
    summaries = await rules.team_summaries([team])
    return _read(team, summaries[team.id])
