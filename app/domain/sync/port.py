from datetime import datetime
from typing import Protocol

from app.domain.sync.source import (
    SourceCodebase,
    SourceDeployment,
    SourceProject,
    SourcePullRequest,
    SourceTeam,
    SourceWorkItem,
)


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

    async def fetch_work_items(self, team_external_id: str | None = None) -> list[SourceWorkItem]:
        """Every work item, or only one team's when team_external_id is given."""
        ...

    async def fetch_organization_name(self) -> str:
        """Name of the workspace the credentials are scoped to."""
        ...


class CodeHostSource(Protocol):
    """Port for an external code host (repositories, pull requests, deployments)."""

    async def fetch_codebases(self) -> list[SourceCodebase]: ...

    async def fetch_pull_requests(
        self, codebase_external_id: str, since: datetime
    ) -> list[SourcePullRequest]:
        """Every pull request updated at or after `since`."""
        ...

    async def fetch_deployments(
        self, codebase_external_id: str, since: datetime
    ) -> list[SourceDeployment]:
        """Every deployment created at or after `since`, in any environment."""
        ...
