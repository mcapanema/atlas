from typing import Protocol

from app.domain.sync.source import SourceProject, SourceTeam, SourceWorkItem


class DataSourceError(Exception):
    """An external delivery system failed (HTTP error, bad payload, timeout).

    Raised by DeliveryDataSource implementations; Presentation maps it to 502.
    Deliberately not a ValueError — the global ValueError handler returns 422
    blaming the client, which is wrong for an upstream failure.
    """


class DeliveryDataSource(Protocol):
    """Port for an external delivery system. Implemented by connectors in Infrastructure."""

    async def fetch_teams(self) -> list[SourceTeam]: ...

    async def fetch_projects(self) -> list[SourceProject]: ...

    async def fetch_work_items(self) -> list[SourceWorkItem]: ...
