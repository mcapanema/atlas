"""Vendor-neutral GraphQL-over-HTTP client with bounded retries.

Each vendor adapter supplies the URL, auth headers, a display name for
messages, and the `DataSourceError` subclass to raise.
"""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import httpx

from app.domain.sync.port import DataSourceError

_MAX_ATTEMPTS = 3

# Network failures a retry can outlive. Not retried: a read/write timeout
# (the vendor accepted the connection and is hanging, so a retry triples the
# worst case), a pool timeout (each attempt opens a fresh pool, so it
# signals local exhaustion), and permanent misconfiguration
# (UnsupportedProtocol, ProxyError, LocalProtocolError).
_RETRYABLE_TRANSPORT_ERRORS: tuple[type[httpx.TransportError], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)

# Connecting gets its own short timeout so a DNS/connect outage fails fast.
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

# Seam for tests: monkeypatch this to record delays instead of sleeping.
_sleep = asyncio.sleep

logger = logging.getLogger(__name__)


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    # ponytail: only the integer-seconds Retry-After form is honored; the
    # HTTP-date form falls back to exponential backoff. Parse the date form
    # if a vendor ever starts sending it.
    if retry_after is not None and retry_after.isdigit():
        return float(retry_after)
    return float(2 ** (attempt - 1))


def _retry_reason(outcome: httpx.Response | httpx.TransportError) -> str | None:
    """Why this attempt is worth repeating, or None if it isn't."""
    if isinstance(outcome, httpx.TransportError):
        return f"request failed ({outcome})"
    status = outcome.status_code
    # 403 + Retry-After is GitHub's secondary rate limit; a bare 403 is auth.
    if status == 429 or status >= 500 or (status == 403 and "Retry-After" in outcome.headers):
        return f"returned HTTP {status}"
    return None


class GraphQLClient:
    def __init__(
        self,
        url: str,
        headers: Mapping[str, str],
        *,
        vendor: str,
        error: type[DataSourceError],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._headers = dict(headers)
        self._vendor = vendor
        self._error = error
        self._transport = transport

    async def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        attempt = 1
        while True:
            outcome = await self._post(query, variables)
            reason = _retry_reason(outcome)
            if reason is not None and attempt < _MAX_ATTEMPTS:
                retry_after = (
                    outcome.headers.get("Retry-After")
                    if isinstance(outcome, httpx.Response)
                    else None
                )
                delay = _retry_delay(retry_after, attempt)
                logger.warning(
                    "%s API %s; retrying in %.0fs (attempt %d/%d)",
                    self._vendor,
                    reason,
                    delay,
                    attempt,
                    _MAX_ATTEMPTS,
                )
                await _sleep(delay)
                attempt += 1
                continue
            if isinstance(outcome, httpx.TransportError):
                raise self._error(f"{self._vendor} API request failed: {outcome}") from outcome
            return self._parse(outcome)

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        vendor = self._vendor
        if response.status_code != 200:
            raise self._error(f"{vendor} API returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise self._error(f"{vendor} response is not JSON") from exc
        if not isinstance(payload, dict):
            raise self._error(f"{vendor} response is not an object")
        if payload.get("errors"):
            raise self._error(f"{vendor} GraphQL errors: {payload['errors']}")
        data: dict[str, Any] | None = payload.get("data")
        if data is None:
            raise self._error(f"{vendor} response has no data")
        return data

    async def _post(
        self, query: str, variables: dict[str, Any] | None
    ) -> httpx.Response | httpx.TransportError:
        """The response, or a network failure in _RETRYABLE_TRANSPORT_ERRORS."""
        # ponytail: a fresh connection per attempt. Hold a pooled AsyncClient
        # (with aclose()) if sync latency over many pages ever matters.
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=_TIMEOUT) as http:
                return await http.post(
                    self._url,
                    json={"query": query, "variables": variables or {}},
                    headers=self._headers,
                )
        except _RETRYABLE_TRANSPORT_ERRORS as exc:
            return exc
        except httpx.HTTPError as exc:
            raise self._error(f"{self._vendor} API request failed: {exc}") from exc
