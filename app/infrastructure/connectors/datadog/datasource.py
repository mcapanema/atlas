"""CodeHostSource and IncidentSource adapter backed by Datadog's REST API."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.domain._time import utcnow
from app.domain.codebases.entities import CodebaseSource
from app.domain.sync.source import (
    SourceCodebase,
    SourceDeployment,
    SourceIncident,
    SourcePullRequest,
)
from app.infrastructure.connectors.datadog.client import DatadogClient
from app.infrastructure.connectors.datadog.mapping import (
    map_deployment,
    map_incident,
    map_service,
    parse_time,
)
from app.infrastructure.connectors.graphql import map_tolerantly

# ponytail: 1000 pages bounds one sync per loop (100k services or incidents,
# 500k deployments per service); it mainly guards against a paging loop.
_MAX_PAGES = 1000
_PAGE_SIZE = 100
_DEPLOYMENT_LIMIT = 500
_SERVICE_PREFIX = "datadog:service:"


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _deployments_body(name: str, since: datetime, now: datetime) -> dict[str, Any]:
    return {
        "data": {
            "type": "dora_deployments_list_request",
            "attributes": {
                "query": f"service:{_quote(name)}",
                "from": since.isoformat(),
                "to": now.isoformat(),
                "sort": "started_at",
                "limit": _DEPLOYMENT_LIMIT,
            },
        }
    }


def _is_wanted(node: dict[str, Any], since: datetime) -> bool:
    """Drop test incidents and ones modified before `since`; an unreadable stamp stays in."""
    attributes = node.get("attributes") or {}
    if attributes.get("is_test"):
        return False
    try:
        return parse_time(attributes["modified"]) >= since
    except (KeyError, TypeError, ValueError):
        return True


class DatadogDataSource:
    source = CodebaseSource.DATADOG

    def __init__(
        self, client: DatadogClient, site: str, *, now: Callable[[], datetime] = utcnow
    ) -> None:
        self._client = client
        self._site = site
        self._now = now

    async def fetch_codebases(self) -> list[SourceCodebase]:
        nodes: list[dict[str, Any]] = []
        for page_number in range(_MAX_PAGES):
            params: dict[str, str | int] = {
                "filter[kind]": "service",
                "includeDiscovered": "true",
                "page[limit]": _PAGE_SIZE,
                "page[offset]": page_number * _PAGE_SIZE,
            }
            page = (await self._client.get("/api/v2/catalog/entity", params))["data"]
            nodes.extend(page)
            if len(page) < _PAGE_SIZE:
                break
        return map_tolerantly(nodes, map_service, "service", vendor="Datadog")

    async def fetch_pull_requests(
        self, codebase_external_id: str, since: datetime
    ) -> list[SourcePullRequest]:
        return []

    async def fetch_deployments(
        self, codebase_external_id: str, since: datetime
    ) -> list[SourceDeployment]:
        name = codebase_external_id.removeprefix(_SERVICE_PREFIX)
        now = self._now()
        cursor = since
        seen: dict[str, dict[str, Any]] = {}
        for _ in range(_MAX_PAGES):
            body = _deployments_body(name, cursor, now)
            page = (await self._client.post("/api/v2/dora/deployments", body))["data"]
            for node in page:
                seen.setdefault(node["id"], node)
            if len(page) < _DEPLOYMENT_LIMIT:
                break
            last = parse_time(page[-1]["attributes"]["started_at"])
            if last <= cursor:
                # ponytail: more than _DEPLOYMENT_LIMIT deployments share one
                # started_at; the rest are skipped.
                break
            cursor = last
        return map_tolerantly(list(seen.values()), map_deployment, "deployment", vendor="Datadog")

    async def fetch_incidents(self, since: datetime) -> list[SourceIncident]:
        nodes: list[dict[str, Any]] = []
        offset = 0
        for _ in range(_MAX_PAGES):
            params = {"page[size]": _PAGE_SIZE, "page[offset]": offset}
            payload = await self._client.get("/api/v2/incidents", params)
            nodes.extend(payload["data"])
            next_offset = ((payload.get("meta") or {}).get("pagination") or {}).get("next_offset")
            if len(payload["data"]) < _PAGE_SIZE or next_offset is None:
                break
            offset = next_offset
        wanted = [node for node in nodes if _is_wanted(node, since)]
        return map_tolerantly(
            wanted, lambda node: map_incident(node, self._site), "incident", vendor="Datadog"
        )
