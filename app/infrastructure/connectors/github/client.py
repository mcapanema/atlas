"""Minimal GraphQL-over-HTTP client for GitHub.

Auth is a personal access token sent as a Bearer header. Retry and parse
logic lives in the shared `GraphQLClient`.
"""

import httpx

from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors.graphql import GraphQLClient

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"


class GitHubAPIError(DataSourceError):
    """The GitHub API returned an HTTP or GraphQL-level error."""


class GitHubGraphQLClient(GraphQLClient):
    def __init__(
        self,
        token: str,
        base_url: str = GITHUB_GRAPHQL_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url,
            {"Authorization": f"Bearer {token}"},
            vendor="GitHub",
            error=GitHubAPIError,
            transport=transport,
        )
