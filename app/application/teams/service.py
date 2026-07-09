from uuid import UUID

from app.domain.teams.entities import Team
from app.domain.teams.repository import TeamRepository


class TeamService:
    """Application use cases for Teams."""

    def __init__(self, repository: TeamRepository) -> None:
        self._repository = repository

    async def create_team(
        self, organization_id: UUID, name: str, external_id: str | None = None
    ) -> Team:
        team = Team(organization_id=organization_id, name=name, external_id=external_id)
        await self._repository.add(team)
        return team

    async def list_teams(self) -> list[Team]:
        return await self._repository.list()
