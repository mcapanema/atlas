from uuid import uuid4

from app.application.teams.service import TeamService
from tests.fakes import InMemoryTeamRepository


async def test_create_team_persists_and_returns() -> None:
    repo = InMemoryTeamRepository()
    service = TeamService(repo)
    org_id = uuid4()

    team = await service.create_team(organization_id=org_id, name="Platform")

    assert team.organization_id == org_id
    assert team.name == "Platform"
    assert await repo.get(team.id) is team


async def test_list_teams_returns_all() -> None:
    repo = InMemoryTeamRepository()
    service = TeamService(repo)
    await service.create_team(organization_id=uuid4(), name="Platform")
    await service.create_team(organization_id=uuid4(), name="Growth")

    teams = await service.list_teams()

    assert {t.name for t in teams} == {"Platform", "Growth"}


async def test_get_team_returns_none_for_unknown_id() -> None:
    service = TeamService(InMemoryTeamRepository())

    assert await service.get_team(uuid4()) is None


async def test_get_team_returns_created_team() -> None:
    repo = InMemoryTeamRepository()
    service = TeamService(repo)
    team = await service.create_team(organization_id=uuid4(), name="Platform")

    assert await service.get_team(team.id) is team
