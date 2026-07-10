"""Minimal GraphQL-over-HTTP client for Linear.

Auth is a Linear personal API key, sent raw in the Authorization header
(Linear does not use a Bearer prefix for personal keys).
"""

import asyncio
import logging
from typing import Any

import httpx

from app.domain.sync.port import DataSourceError

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"

_MAX_ATTEMPTS = 3

# Seam for tests: monkeypatch this to record delays instead of sleeping.
_sleep = asyncio.sleep

logger = logging.getLogger(__name__)


class LinearAPIError(DataSourceError):
    """The Linear API returned an HTTP or GraphQL-level error."""


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    # ponytail: only the integer-seconds Retry-After form is honored; the
    # HTTP-date form falls back to exponential backoff. Parse the date form
    # if Linear ever starts sending it.
    if retry_after is not None and retry_after.isdigit():
        return float(retry_after)
    return float(2 ** (attempt - 1))


def _parse(response: httpx.Response) -> dict[str, Any]:
    if response.status_code != 200:
        raise LinearAPIError(f"Linear API returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise LinearAPIError("Linear response is not JSON") from exc
    if not isinstance(payload, dict):
        raise LinearAPIError("Linear response is not an object")
    if payload.get("errors"):
        raise LinearAPIError(f"Linear GraphQL errors: {payload['errors']}")
    data: dict[str, Any] | None = payload.get("data")
    if data is None:
        raise LinearAPIError("Linear response has no data")
    return data


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
        attempt = 1
        while True:
            response = await self._post(query, variables)
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < _MAX_ATTEMPTS:
                delay = _retry_delay(response.headers.get("Retry-After"), attempt)
                logger.warning(
                    "Linear API returned HTTP %d; retrying in %.0fs (attempt %d/%d)",
                    response.status_code,
                    delay,
                    attempt,
                    _MAX_ATTEMPTS,
                )
                await _sleep(delay)
                attempt += 1
                continue
            return _parse(response)

    async def _post(self, query: str, variables: dict[str, Any] | None) -> httpx.Response:
        # ponytail: a fresh connection per attempt. Hold a pooled AsyncClient
        # (with aclose()) if sync latency over many pages ever matters.
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as http:
                return await http.post(
                    self._base_url,
                    json={"query": query, "variables": variables or {}},
                    headers={"Authorization": self._api_key},
                )
        except httpx.HTTPError as exc:
            raise LinearAPIError(f"Linear API request failed: {exc}") from exc
