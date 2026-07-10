"""Minimal GraphQL-over-HTTP client for Linear.

Auth is a Linear personal API key, sent raw in the Authorization header
(Linear does not use a Bearer prefix for personal keys).
"""

from typing import Any

import httpx

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


class LinearAPIError(Exception):
    """The Linear API returned an HTTP or GraphQL-level error."""


class LinearGraphQLClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = LINEAR_GRAPHQL_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._transport = transport

    async def execute(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        # ponytail: a fresh connection per call. Hold a pooled AsyncClient
        # (with aclose()) if sync latency over many pages ever matters.
        async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as http:
            response = await http.post(
                self._base_url,
                json={"query": query, "variables": variables or {}},
                headers={"Authorization": self._api_key},
            )
        if response.status_code != 200:
            raise LinearAPIError(f"Linear API returned HTTP {response.status_code}")
        payload: dict[str, Any] = response.json()
        if payload.get("errors"):
            raise LinearAPIError(f"Linear GraphQL errors: {payload['errors']}")
        data: dict[str, Any] | None = payload.get("data")
        if data is None:
            raise LinearAPIError("Linear response has no data")
        return data
