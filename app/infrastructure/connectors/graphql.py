"""Vendor-neutral GraphQL-over-HTTP client with bounded retries.

Each vendor adapter supplies the URL, auth headers, a display name for
messages, and the `DataSourceError` subclass to raise.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors.retry import send_with_retries

logger = logging.getLogger(__name__)


_MAX_ERROR_KINDS = 5


def _describe_error(error: Any) -> str:
    """`TYPE at a.*.b: message`, with list indices as `*` so per-node errors collapse."""
    if not isinstance(error, dict) or "message" not in error:
        return str(error)
    path = ".".join("*" if isinstance(p, int) else str(p) for p in error.get("path") or [])
    where = " ".join(part for part in (error.get("type"), path and f"at {path}") if part)
    return f"{where}: {error['message']}" if where else str(error["message"])


def _summarize_errors(errors: list[Any]) -> str:
    """Distinct error kinds in first-seen order; a page can return one error per node."""
    kinds = list(dict.fromkeys(_describe_error(e) for e in errors))
    summary = "; ".join(kinds[:_MAX_ERROR_KINDS])
    if len(kinds) > _MAX_ERROR_KINDS:
        summary += f"; …and {len(kinds) - _MAX_ERROR_KINDS} more"
    elif len(errors) > len(kinds):
        summary += f" ({len(errors)} errors)"
    return summary


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
        response = await send_with_retries(
            lambda http: http.post(
                self._url,
                json={"query": query, "variables": variables or {}},
                headers=self._headers,
            ),
            vendor=self._vendor,
            error=self._error,
            transport=self._transport,
        )
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        vendor = self._vendor
        if response.status_code != 200:
            raise self._error(
                f"{vendor} API returned HTTP {response.status_code}", status=response.status_code
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise self._error(f"{vendor} response is not JSON") from exc
        if not isinstance(payload, dict):
            raise self._error(f"{vendor} response is not an object")
        if payload.get("errors"):
            raise self._error(
                f"{vendor} GraphQL errors: {_summarize_errors(payload['errors'])}",
                status=response.status_code,
            )
        data: dict[str, Any] | None = payload.get("data")
        if data is None:
            raise self._error(f"{vendor} response has no data")
        return data


def map_tolerantly[T](
    nodes: list[dict[str, Any]],
    mapper: Callable[[dict[str, Any]], T],
    kind: str,
    *,
    vendor: str,
) -> list[T]:
    """Map nodes one by one; a malformed node is skipped and logged, not fatal."""
    mapped: list[T] = []
    skipped = 0
    for node in nodes:
        try:
            mapped.append(mapper(node))
        except (KeyError, IndexError, TypeError, ValueError):
            skipped += 1
            logger.warning(
                "Skipping malformed %s %s node %s",
                vendor,
                kind,
                node.get("id", "<no id>"),
                exc_info=True,
            )
    if skipped:
        logger.warning("Skipped %d malformed %s %s node(s)", skipped, vendor, kind)
    return mapped
