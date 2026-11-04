from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.metrics.dora import DoraService
from app.application.scope import ScopeSamples
from app.domain.codebases.entities import Codebase, CodebaseSource, Deployment, DeploymentStatus
from app.domain.incidents.entities import ServiceIncident
from app.domain.metric_rules.entities import DEFAULT_RULES, IncidentSource
from app.domain.metrics.samples import FlowSample
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from tests.fakes import (
    InMemoryCodebaseRepository,
    InMemoryDeploymentRepository,
    InMemoryPullRequestRepository,
    InMemoryServiceIncidentRepository,
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


def _service(
    team: Team,
    codebases: list[Codebase],
    deployments: list[Deployment],
    incidents: list[ServiceIncident] | None = None,
) -> DoraService:
    return DoraService(
        InMemoryCodebaseRepository(codebases),
        InMemoryDeploymentRepository(deployments),
        InMemoryPullRequestRepository(),
        InMemoryTeamRepository([team]),
        InMemoryServiceIncidentRepository(incidents),
    )


def _scope(
    items: list[tuple[WorkItem, FlowSample]] | None = None,
    health_min_sample: int = 5,
    incident_source: IncidentSource = "auto",
) -> ScopeSamples:
    return ScopeSamples(
        streams=[],
        samples=[],
        item_count=0,
        items_with_samples=items or [],
        rules=replace(
            DEFAULT_RULES, health_min_sample=health_min_sample, incident_source=incident_source
        ),
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


def _datadog(team: Team, name: str = "api") -> Codebase:
    return Codebase(
        organization_id=ORG,
        name=name,
        external_id=f"datadog:service:{name}",
        team_id=team.id,
        source=CodebaseSource.DATADOG,
    )


def _outage(*services: str) -> ServiceIncident:
    return ServiceIncident(
        organization_id=ORG,
        external_id=str(uuid4()),
        title="Outage",
        opened_at=_days_ago(3),
        restored_at=_days_ago(2),
        services=services,
    )


async def _restores(
    incidents: list[ServiceIncident],
    source: IncidentSource = "auto",
    codebase: Codebase | None = None,
    linear: int = 1,
) -> int:
    team = Team(organization_id=ORG, name="A")
    mapped = codebase or _datadog(team)
    mapped = replace(mapped, team_id=team.id)
    items = [_incident(team, ("incident",)) for _ in range(linear)]
    service = _service(team, [mapped], [], incidents)
    result = await service.get_dora(
        team_id=team.id, scope=_scope(items, incident_source=source), now=NOW
    )
    return result.restores


async def test_both_tools_reporting_one_release_count_one_deployment() -> None:
    team = Team(organization_id=ORG, name="A")
    github = Codebase(organization_id=ORG, name="a", external_id="a", team_id=team.id)
    datadog = _datadog(team)
    service = _service(team, [github, datadog], [_deploy(github, 1), _deploy(datadog, 1)])

    result = await service.get_dora(team_id=team.id, scope=_scope(), now=NOW)

    assert result.deployments == 1
    assert result.duplicate_deployments == 1


async def test_auto_uses_datadog_incidents_when_the_team_has_any() -> None:
    assert await _restores([_outage("API ")]) == 1


async def test_auto_uses_a_datadog_incident_outside_the_window() -> None:
    old = replace(_outage("api"), opened_at=_days_ago(400), restored_at=_days_ago(399))

    assert await _restores([old], linear=1) == 0


async def test_auto_falls_back_to_linear_without_datadog_incidents() -> None:
    assert await _restores([]) == 1


async def test_linear_rule_ignores_datadog_incidents() -> None:
    assert await _restores([_outage("api"), _outage("api")], "linear") == 1


async def test_datadog_rule_ignores_linear_incidents() -> None:
    assert await _restores([_outage("api")], "datadog", linear=3) == 1


async def test_datadog_incident_on_an_unmapped_service_counts_nowhere() -> None:
    assert await _restores([_outage("billing")], "datadog", linear=0) == 0


async def test_auto_keeps_linear_when_no_incident_matches_the_mapped_services() -> None:
    assert await _restores([_outage("billing")]) == 1


async def test_github_codebase_with_the_same_name_does_not_match_incidents() -> None:
    team = Team(organization_id=ORG, name="A")
    github = Codebase(organization_id=ORG, name="api", external_id="gh", team_id=team.id)

    assert await _restores([_outage("api")], "datadog", github, linear=0) == 0
