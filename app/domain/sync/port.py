from typing import Protocol

from app.domain.sync.source import SourceProject, SourceTeam, SourceWorkItem


class DeliveryDataSource(Protocol):
    """Port for an external delivery system. Implemented by connectors in Infrastructure."""

    async def fetch_teams(self) -> list[SourceTeam]: ...

    async def fetch_projects(self) -> list[SourceProject]: ...

    async def fetch_work_items(self) -> list[SourceWorkItem]: ...
