from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.codebases.service import (
    CodebaseOverview,
    CodebaseService,
    UnknownCodebaseError,
)
from app.domain.codebases.entities import Codebase, Deployment, PullRequest
from app.domain.organizations.entities import Organization
from app.domain.teams.entities import Team
from tests.fakes import (
    InMemoryCodebaseRepository,
    InMemoryDeploymentRepository,
    InMemoryPullRequestRepository,
    InMemoryTeamRepository,
)

T = datetime(2026, 10, 20, tzinfo=UTC)


async def build(
    codebases: list[Codebase] | None = None,
    teams: list[Team] | None = None,
    pull_requests: list[PullRequest] | None = None,
    deployments: list[Deployment] | None = None,
) -> CodebaseService:
    team_repo = InMemoryTeamRepository()
    for team in teams or []:
        await team_repo.add(team)
    return CodebaseService(
        InMemoryCodebaseRepository(codebases),
        team_repo,
        InMemoryPullRequestRepository(pull_requests),
        InMemoryDeploymentRepository(deployments),
    )


async def test_list_returns_counts_sorted_by_name() -> None:
    org = Organization(name="Acme")
    web = Codebase(organization_id=org.id, name="acme/web", external_id="w")
    api = Codebase(organization_id=org.id, name="acme/api", external_id="a")
    other = Codebase(organization_id=uuid4(), name="acme/other", external_id="o")
    service = await build(
        [web, api, other],
        pull_requests=[
            PullRequest(codebase_id=api.id, external_id="p1", number=1, title="x", opened_at=T),
            PullRequest(codebase_id=api.id, external_id="p2", number=2, title="y", opened_at=T),
        ],
        deployments=[
            Deployment(
                codebase_id=web.id,
                external_id="d1",
                environment="production",
                sha="s",
                started_at=T,
            )
        ],
    )

    assert await service.list(org.id) == [
        CodebaseOverview(codebase=api, pull_requests=2, deployments=0),
        CodebaseOverview(codebase=web, pull_requests=0, deployments=1),
    ]


async def test_update_maps_team_and_environment() -> None:
    org = Organization(name="Acme")
    team = Team(organization_id=org.id, name="Platform")
    codebase = Codebase(organization_id=org.id, name="acme/api", external_id="a")
    service = await build([codebase], [team])

    updated = await service.update(codebase.id, team_id=team.id, production_environment=" prod ")

    assert (updated.team_id, updated.production_environment) == (team.id, "prod")
    assert (await service.list(org.id))[0].codebase.team_id == team.id


async def test_update_can_unmap_a_codebase() -> None:
    org = Organization(name="Acme")
    team = Team(organization_id=org.id, name="Platform")
    codebase = Codebase(organization_id=org.id, name="acme/api", external_id="a", team_id=team.id)
    service = await build([codebase], [team])

    updated = await service.update(codebase.id, team_id=None, production_environment="production")

    assert updated.team_id is None


async def test_update_rejects_team_of_another_organization() -> None:
    org = Organization(name="Acme")
    foreign = Team(organization_id=uuid4(), name="Elsewhere")
    codebase = Codebase(organization_id=org.id, name="acme/api", external_id="a")
    service = await build([codebase], [foreign])

    with pytest.raises(ValueError, match="Team"):
        await service.update(codebase.id, team_id=foreign.id, production_environment="production")


async def test_update_rejects_unknown_team_and_blank_environment() -> None:
    org = Organization(name="Acme")
    team = Team(organization_id=org.id, name="Platform")
    codebase = Codebase(organization_id=org.id, name="acme/api", external_id="a")
    service = await build([codebase], [team])

    with pytest.raises(ValueError, match="Team"):
        await service.update(codebase.id, team_id=uuid4(), production_environment="production")
    with pytest.raises(ValueError, match="production_environment"):
        await service.update(codebase.id, team_id=team.id, production_environment="  ")


async def test_update_unknown_codebase_raises() -> None:
    service = await build()
    with pytest.raises(UnknownCodebaseError):
        await service.update(uuid4(), team_id=None, production_environment="production")
