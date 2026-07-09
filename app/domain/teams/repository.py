from typing import Protocol
from uuid import UUID

from app.domain.teams.entities import Team


class TeamRepository(Protocol):
    """Port for persisting and retrieving Teams. Implemented in Infrastructure."""

    async def add(self, team: Team) -> None: ...

    async def list(self) -> list[Team]: ...

    async def get(self, team_id: UUID) -> Team | None: ...

    async def get_by_external_id(self, external_id: str) -> Team | None: ...
