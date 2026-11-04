import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.domain.codebases.entities import CodebaseSource
from app.domain.sync.port import DatadogSource
from app.infrastructure.connectors.datadog.client import DatadogClient
from app.infrastructure.connectors.datadog.datasource import DatadogDataSource

NOW = datetime(2024, 6, 1, tzinfo=UTC)
SINCE = datetime(2024, 1, 1, tzinfo=UTC)


def _source(handler: Callable[[httpx.Request], httpx.Response]) -> DatadogDataSource:
    client = DatadogClient("k", "a", "datadoghq.com", transport=httpx.MockTransport(handler))
    return DatadogDataSource(client, "datadoghq.com", now=lambda: NOW)


def test_datadog_data_source_satisfies_the_port() -> None:
    client = DatadogClient("k", "a", "datadoghq.com")
    source: DatadogSource = DatadogDataSource(client, "datadoghq.com")
    assert source.source is CodebaseSource.DATADOG


async def test_pull_requests_are_always_empty() -> None:
    source = _source(lambda request: httpx.Response(500))
    assert await source.fetch_pull_requests("datadog:service:api", SINCE) == []


async def test_fetch_codebases_pages_the_catalog_until_a_short_page() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        offset = int(request.url.params["page[offset]"])
        count = 100 if offset == 0 else 3
        data = [{"attributes": {"name": f"s{offset + i}"}} for i in range(count)]
        return httpx.Response(200, json={"data": data})

    codebases = await _source(handler).fetch_codebases()

    assert len(codebases) == 103
    assert [r.url.params["page[offset]"] for r in requests] == ["0", "100"]
    assert requests[0].url.params["filter[kind]"] == "service"
    assert requests[0].url.params["includeDiscovered"] == "true"
    assert requests[0].url.params["page[limit]"] == "100"


def _deployment(i: int, started_at: str) -> dict[str, Any]:
    return {"id": f"d{i}", "attributes": {"started_at": started_at}}


async def test_fetch_deployments_quotes_and_escapes_the_service_name() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"data": []})

    await _source(handler).fetch_deployments('datadog:service:a "b"', SINCE)

    data = bodies[0]["data"]
    attributes = data["attributes"]
    assert data["type"] == "dora_deployments_list_request"
    assert attributes["query"] == 'service:"a \\"b\\""'
    assert attributes["from"] == SINCE.isoformat()
    assert attributes["to"] == NOW.isoformat()
    assert attributes["sort"] == "started_at"
    assert attributes["limit"] == 500


async def test_fetch_deployments_advances_from_to_the_last_started_at() -> None:
    bodies: list[dict[str, Any]] = []
    last = "2024-03-01T00:00:00+00:00"

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            page = [_deployment(i, "2024-02-01T00:00:00+00:00") for i in range(499)]
            page.append(_deployment(499, last))
        else:
            # The boundary event repeats, plus new ones; the page is short.
            page = [_deployment(499, last), _deployment(500, last), _deployment(501, last)]
        return httpx.Response(200, json={"data": page})

    deployments = await _source(handler).fetch_deployments("datadog:service:api", SINCE)

    assert bodies[1]["data"]["attributes"]["from"] == datetime(2024, 3, 1, tzinfo=UTC).isoformat()
    assert len(deployments) == 502
    assert len({d.external_id for d in deployments}) == 502


async def test_fetch_deployments_stops_when_from_does_not_advance() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        page = [_deployment(i, "2024-02-01T00:00:00+00:00") for i in range(500)]
        return httpx.Response(200, json={"data": page})

    deployments = await _source(handler).fetch_deployments("datadog:service:api", SINCE)

    assert calls == 2
    assert len(deployments) == 500


def _incident(i: int, modified: datetime, *, test: bool = False) -> dict[str, Any]:
    return {
        "id": f"i{i}",
        "attributes": {
            "title": "t",
            "public_id": i,
            "created": "2024-05-01T00:00:00+00:00",
            "modified": modified.isoformat(),
            "is_test": test,
        },
    }


async def test_fetch_incidents_follows_next_offset_and_drops_old_and_test_incidents() -> None:
    offsets: list[str] = []
    recent = SINCE + timedelta(days=10)

    def handler(request: httpx.Request) -> httpx.Response:
        offset = request.url.params["page[offset]"]
        offsets.append(offset)
        assert request.url.params["page[size]"] == "100"
        if offset == "0":
            data = [_incident(i, recent) for i in range(98)]
            data.append(_incident(98, SINCE - timedelta(days=1)))
            data.append(_incident(99, recent, test=True))
            body = {"data": data, "meta": {"pagination": {"next_offset": 100}}}
        else:
            body = {"data": [_incident(100, recent)], "meta": {"pagination": {}}}
        return httpx.Response(200, json=body)

    incidents = await _source(handler).fetch_incidents(SINCE)

    assert offsets == ["0", "100"]
    assert len(incidents) == 99
    ids = {i.external_id for i in incidents}
    assert ids.isdisjoint({"datadog:incident:i98", "datadog:incident:i99"})
