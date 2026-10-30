from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.codebases.entities import Codebase, Deployment, DeploymentStatus, PullRequest
from app.domain.organizations.entities import Organization
from app.domain.teams.entities import Team
from app.infrastructure.repositories.codebases import (
    SqlAlchemyCodebaseRepository,
    SqlAlchemyDeploymentRepository,
    SqlAlchemyPullRequestRepository,
)
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository

T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def _org(session: AsyncSession, name: str = "Acme") -> UUID:
    org = Organization(name=name)
    await SqlAlchemyOrganizationRepository(session).add(org)
    return org.id


async def _codebase(session: AsyncSession, external_id: str = "r1") -> Codebase:
    codebase = Codebase(
        organization_id=await _org(session, external_id), name="api", external_id=external_id
    )
    await SqlAlchemyCodebaseRepository(session).add(codebase)
    return codebase


def _pr(codebase: Codebase, external_id: str, number: int = 1) -> PullRequest:
    return PullRequest(
        codebase_id=codebase.id,
        external_id=external_id,
        number=number,
        title="T",
        opened_at=T0,
    )


def _deployment(codebase: Codebase, external_id: str) -> Deployment:
    return Deployment(
        codebase_id=codebase.id,
        external_id=external_id,
        environment="production",
        sha="abc",
        started_at=T0,
    )


async def test_codebase_round_trip_and_list_by_organization(session: AsyncSession) -> None:
    repo = SqlAlchemyCodebaseRepository(session)
    org_a, org_b = await _org(session, "A"), await _org(session, "B")
    a = Codebase(
        organization_id=org_a,
        name="api",
        external_id="a",
        url="https://x/a",
        last_synced_at=T0,
    )
    b = Codebase(organization_id=org_b, name="web", external_id="b")
    await repo.add(a)
    await repo.add(b)
    session.expire_all()
    assert await repo.list(org_a) == [a]
    assert await repo.get(b.id) == b
    assert await repo.get(uuid4()) is None


async def test_codebase_get_by_external_ids_spans_organizations(session: AsyncSession) -> None:
    repo = SqlAlchemyCodebaseRepository(session)
    a, b = await _codebase(session, "a"), await _codebase(session, "b")
    session.expire_all()
    assert a.organization_id != b.organization_id
    assert await repo.get_by_external_ids(["a", "b", "missing"]) == {"a": a, "b": b}
    assert await repo.get_by_external_ids([]) == {}


async def test_codebase_update_maps_team(session: AsyncSession) -> None:
    repo = SqlAlchemyCodebaseRepository(session)
    codebase = await _codebase(session)
    team = Team(organization_id=codebase.organization_id, name="Platform")
    await SqlAlchemyTeamRepository(session).add(team)
    codebase.team_id = team.id
    codebase.last_synced_at = T0
    await repo.update(codebase)
    session.expire_all()
    assert await repo.get(codebase.id) == codebase


async def test_pull_request_get_by_external_ids_round_trips_keys(session: AsyncSession) -> None:
    codebase = await _codebase(session)
    repo = SqlAlchemyPullRequestRepository(session)
    pr = _pr(codebase, "pr1")
    pr.url = "https://x/1"
    pr.merged_at = T0
    pr.merge_commit_sha = "abc"
    pr.work_item_keys = ("OPS-1", "ENG-2")
    await repo.add(pr)
    session.expire_all()
    found = await repo.get_by_external_ids(["pr1", "nope"])
    assert found == {"pr1": pr}
    assert found["pr1"].work_item_keys == ("OPS-1", "ENG-2")


async def test_pull_request_update(session: AsyncSession) -> None:
    codebase = await _codebase(session)
    repo = SqlAlchemyPullRequestRepository(session)
    pr = _pr(codebase, "pr1")
    await repo.add(pr)
    pr.closed_at = T0
    pr.work_item_keys = ("OPS-9",)
    await repo.update(pr)
    session.expire_all()
    assert (await repo.get_by_external_ids(["pr1"]))["pr1"] == pr


async def test_get_by_external_ids_batches_past_the_bind_limit(session: AsyncSession) -> None:
    ids = [f"x{i}" for i in range(1200)]
    assert await SqlAlchemyPullRequestRepository(session).get_by_external_ids(ids) == {}
    assert await SqlAlchemyDeploymentRepository(session).get_by_external_ids(ids) == {}


async def test_deployment_update_changes_status_and_finished_at(session: AsyncSession) -> None:
    codebase = await _codebase(session)
    repo = SqlAlchemyDeploymentRepository(session)
    deployment = _deployment(codebase, "d1")
    await repo.add(deployment)
    deployment.status = DeploymentStatus.SUCCESS
    deployment.finished_at = T0
    await repo.update(deployment)
    session.expire_all()
    assert (await repo.get_by_external_ids(["d1"]))["d1"] == deployment


async def test_count_by_codebase_counts_rows_per_codebase(session: AsyncSession) -> None:
    a, b = await _codebase(session, "a"), await _codebase(session, "b")
    prs = SqlAlchemyPullRequestRepository(session)
    deployments = SqlAlchemyDeploymentRepository(session)
    await prs.add(_pr(a, "p1", 1))
    await prs.add(_pr(a, "p2", 2))
    await deployments.add(_deployment(a, "d"))
    assert await prs.count_by_codebase([a.id, b.id]) == {a.id: 2}
    assert await deployments.count_by_codebase([a.id, b.id]) == {a.id: 1}


async def test_list_for_codebases_returns_only_those_codebases(session: AsyncSession) -> None:
    a, b = await _codebase(session, "a"), await _codebase(session, "b")
    prs = SqlAlchemyPullRequestRepository(session)
    deployments = SqlAlchemyDeploymentRepository(session)
    pr_a = _pr(a, "pa")
    await prs.add(pr_a)
    await prs.add(_pr(b, "pb"))
    d_a = _deployment(a, "da")
    await deployments.add(d_a)
    await deployments.add(_deployment(b, "db"))
    session.expire_all()
    assert await prs.list_for_codebases([a.id]) == [pr_a]
    assert await deployments.list_for_codebases([a.id]) == [d_a]
    assert await prs.list_for_codebases([]) == []


async def test_oldest_pending_started_at(session: AsyncSession) -> None:
    a = await _codebase(session, "a")
    b = await _codebase(session, "b")
    repo = SqlAlchemyDeploymentRepository(session)
    t = datetime(2026, 10, 28, tzinfo=UTC)
    for codebase, ext, age, status in [
        (a, "a1", 10, DeploymentStatus.PENDING),
        (a, "a2", 3, DeploymentStatus.PENDING),
        (a, "a3", 5, DeploymentStatus.SUCCESS),
        (b, "b1", 4, DeploymentStatus.PENDING),
    ]:
        row = _deployment(codebase, ext)
        row.started_at = t - timedelta(days=age)
        row.status = status
        await repo.add(row)

    assert await repo.oldest_pending_started_at(a.id, since=t - timedelta(days=7)) == t - timedelta(
        days=3
    )
    assert await repo.oldest_pending_started_at(a.id, since=t - timedelta(days=1)) is None
