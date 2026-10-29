"""Minimal GraphQL-over-HTTP client for Linear.

Auth is a Linear personal API key, sent raw in the Authorization header
(Linear does not use a Bearer prefix for personal keys). Retry and parse
logic lives in the shared `GraphQLClient`.
"""

import httpx

from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors.graphql import GraphQLClient

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


class LinearAPIError(DataSourceError):
    """The Linear API returned an HTTP or GraphQL-level error."""


class LinearGraphQLClient(GraphQLClient):
    def __init__(
        self,
        api_key: str,
        base_url: str = LINEAR_GRAPHQL_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url,
            {"Authorization": api_key},
            vendor="Linear",
            error=LinearAPIError,
            transport=transport,
        )
