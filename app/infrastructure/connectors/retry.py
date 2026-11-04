"""Bounded HTTP retries shared by the connector clients (GraphQL and REST).

`send_with_retries` opens a fresh `httpx.AsyncClient` per attempt, runs the
caller's request on it, and repeats on rate limits, 5xx and transient
network failures.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

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


async def _attempt(
    send: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]],
    *,
    vendor: str,
    error: type[DataSourceError],
    transport: httpx.AsyncBaseTransport | None,
) -> httpx.Response | httpx.TransportError:
    """The response, or a network failure in _RETRYABLE_TRANSPORT_ERRORS."""
    # ponytail: a fresh connection per attempt. Hold a pooled AsyncClient
    # (with aclose()) if sync latency over many pages ever matters.
    try:
        async with httpx.AsyncClient(transport=transport, timeout=_TIMEOUT) as http:
            return await send(http)
    except _RETRYABLE_TRANSPORT_ERRORS as exc:
        return exc
    except httpx.HTTPError as exc:
        raise error(f"{vendor} API request failed: {exc}") from exc


async def send_with_retries(
    send: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]],
    *,
    vendor: str,
    error: type[DataSourceError],
    transport: httpx.AsyncBaseTransport | None,
) -> httpx.Response:
    """The last response (callers judge its status); `error` on a network failure."""
    attempt = 1
    while True:
        outcome = await _attempt(send, vendor=vendor, error=error, transport=transport)
        reason = _retry_reason(outcome)
        if reason is not None and attempt < _MAX_ATTEMPTS:
            retry_after = None
            if isinstance(outcome, httpx.Response):
                headers = outcome.headers
                retry_after = headers.get("Retry-After") or headers.get("X-RateLimit-Reset")
            delay = _retry_delay(retry_after, attempt)
            logger.warning(
                "%s API %s; retrying in %.0fs (attempt %d/%d)",
                vendor,
                reason,
                delay,
                attempt,
                _MAX_ATTEMPTS,
            )
            await _sleep(delay)
            attempt += 1
            continue
        if isinstance(outcome, httpx.TransportError):
            raise error(f"{vendor} API request failed: {outcome}") from outcome
        return outcome
