from uuid import UUID, uuid4

from app.application.teams.service import TeamService
from app.domain.teams.entities import Team


class InMemoryTeamRepository:
    def __init__(self) -> None:
        self._teams: dict[UUID, Team] = {}

    async def add(self, team: Team) -> None:
        self._teams[team.id] = team

    async def list(self) -> list[Team]:
        return list(self._teams.values())

    async def get(self, team_id: UUID) -> Team | None:
        return self._teams.get(team_id)

    async def get_by_external_id(self, external_id: str) -> Team | None:
        return next((t for t in self._teams.values() if t.external_id == external_id), None)


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
