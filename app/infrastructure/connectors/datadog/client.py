"""Minimal REST client for Datadog.

Auth is an API key plus an application key, sent as headers to the regional
`api.<site>` host. Retries live in the shared `send_with_retries`.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors.retry import send_with_retries

_MAX_ERRORS_SHOWN = 3


class DatadogAPIError(DataSourceError):
    """The Datadog API returned an HTTP error or an unusable body."""


class DatadogClient:
    def __init__(
        self,
        api_key: str,
        application_key: str,
        site: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = f"https://api.{site}"
        self._headers = {"DD-API-KEY": api_key, "DD-APPLICATION-KEY": application_key}
        self._transport = transport

    async def get(self, path: str, params: Mapping[str, str | int] | None = None) -> dict[str, Any]:
        return await self._request(
            lambda http: http.get(self._base_url + path, params=params, headers=self._headers)
        )

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            lambda http: http.post(self._base_url + path, json=body, headers=self._headers)
        )

    async def _request(
        self, send: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]]
    ) -> dict[str, Any]:
        response = await send_with_retries(
            send, vendor="Datadog", error=DatadogAPIError, transport=self._transport
        )
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> dict[str, Any]:
        status = response.status_code
        try:
            payload = response.json()
        except ValueError as exc:
            if not response.is_success:
                raise DatadogAPIError(f"Datadog API returned HTTP {status}", status=status) from exc
            raise DatadogAPIError("Datadog response is not JSON") from exc
        if not response.is_success:
            errors = payload.get("errors") if isinstance(payload, dict) else None
            shown = errors[:_MAX_ERRORS_SHOWN] if isinstance(errors, list) else errors
            raise DatadogAPIError(f"Datadog API returned HTTP {status}: {shown}", status=status)
        if not isinstance(payload, dict):
            raise DatadogAPIError("Datadog response is not an object")
        return payload
