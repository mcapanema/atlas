from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.metrics.dora import DoraService
from app.application.scope import ScopeSamples
from app.domain.codebases.entities import Codebase, Deployment, DeploymentStatus
from app.domain.metric_rules.entities import DEFAULT_RULES
from app.domain.metrics.samples import FlowSample
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from tests.fakes import (
    InMemoryCodebaseRepository,
    InMemoryDeploymentRepository,
    InMemoryPullRequestRepository,
    InMemoryTeamRepository,
)

NOW = datetime(2026, 7, 10, tzinfo=UTC)
ORG = uuid4()


def _days_ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


def _deploy(codebase: Codebase, days: int) -> Deployment:
    return Deployment(
        codebase_id=codebase.id,
        external_id=str(uuid4()),
        environment="production",
        sha="abc",
        started_at=_days_ago(days),
        status=DeploymentStatus.SUCCESS,
        finished_at=_days_ago(days),
    )


def _incident(
    team: Team, labels: tuple[str, ...], *, canceled: bool = False
) -> tuple[WorkItem, FlowSample]:
    sample = FlowSample(
        created_at=_days_ago(3),
        started_at=None,
        completed_at=_days_ago(2),
        blocked_time=timedelta(0),
        canceled=canceled,
    )
    return WorkItem(team_id=team.id, title="Outage", labels=labels), sample


def _service(team: Team, codebases: list[Codebase], deployments: list[Deployment]) -> DoraService:
    return DoraService(
        InMemoryCodebaseRepository(codebases),
        InMemoryDeploymentRepository(deployments),
        InMemoryPullRequestRepository(),
        InMemoryTeamRepository([team]),
    )


def _scope(
    items: list[tuple[WorkItem, FlowSample]] | None = None, health_min_sample: int = 5
) -> ScopeSamples:
    return ScopeSamples(
        streams=[],
        samples=[],
        item_count=0,
        items_with_samples=items or [],
        rules=replace(DEFAULT_RULES, health_min_sample=health_min_sample),
    )


async def test_reads_only_the_teams_mapped_codebases() -> None:
    team, other = Team(organization_id=ORG, name="A"), Team(organization_id=ORG, name="B")
    mine = Codebase(organization_id=ORG, name="a", external_id="a", team_id=team.id)
    theirs = Codebase(organization_id=ORG, name="b", external_id="b", team_id=other.id)
    loose = Codebase(organization_id=ORG, name="c", external_id="c")
    deployments = [_deploy(mine, 1)] + [_deploy(theirs, d) for d in (1, 2, 3)]
    deployments += [_deploy(loose, 1), _deploy(loose, 2)]
    service = _service(team, [mine, theirs, loose], deployments)

    result = await service.get_dora(team_id=team.id, scope=_scope(), now=NOW)

    assert result.codebases == 1
    assert result.deployments == 1


async def test_incidents_are_items_with_an_incident_label() -> None:
    team = Team(organization_id=ORG, name="A")
    items = [
        _incident(team, ("Incident",)),
        _incident(team, ("bug",)),
        _incident(team, ("incident",), canceled=True),
    ]
    service = _service(team, [], [])

    result = await service.get_dora(team_id=team.id, scope=_scope(items), now=NOW)

    assert result.restores == 1


async def test_min_sample_is_the_scope_health_floor() -> None:
    team = Team(organization_id=ORG, name="A")
    service = _service(team, [], [])

    result = await service.get_dora(team_id=team.id, scope=_scope(health_min_sample=7), now=NOW)

    assert result.min_sample == 7
