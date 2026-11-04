import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import DATADOG_NOT_CONFIGURED, get_datadog_source, get_delivery_data_source
from app.domain.sync.source import SourceCodebase, SourceIncident, SourceTeam
from tests.api.helpers import settle
from tests.fakes import FakeDataSource, InMemoryDatadogSource


def _source() -> InMemoryDatadogSource:
    return InMemoryDatadogSource(
        codebases=[SourceCodebase(external_id="datadog:service:checkout", name="checkout")],
        incidents=[
            SourceIncident(
                external_id="datadog:incident:1",
                title="Checkout down",
                opened_at=datetime.now(UTC),
                services=("checkout",),
            )
        ],
    )


async def _org(client: AsyncClient) -> str:
    response = await client.post("/api/organizations", json={"name": "Acme"})
    assert response.status_code == 201
    org_id: str = response.json()["id"]
    return org_id


async def test_datadog_sync_is_409_until_configured(rules_client: AsyncClient) -> None:
    response = await rules_client.post("/api/connectors/datadog/sync", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == DATADOG_NOT_CONFIGURED


async def test_datadog_sync_runs_services_deployments_and_incidents(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    rules_app.dependency_overrides[get_datadog_source] = _source
    org_id = await _org(rules_client)

    response = await rules_client.post(
        "/api/connectors/datadog/sync", json={"organization_id": org_id}
    )

    assert response.status_code == 202
    assert response.json()["kind"] == "datadog"
    await settle(rules_app)
    job: dict[str, Any] = (
        await rules_client.get(f"/api/connectors/datadog/jobs/{response.json()['id']}")
    ).json()
    assert job["state"] == "succeeded"
    assert job["summary"] is None
    assert job["code_summary"] is None
    # Deployments 0: the new service is unmapped, so none is fetched.
    assert job["datadog_summary"] == {"codebases": 1, "deployments": 0, "incidents": 1}
    codebases = (await rules_client.get(f"/api/codebases?organization_id={org_id}")).json()
    assert [(c["name"], c["team_id"]) for c in codebases] == [("checkout", None)]


async def test_datadog_sync_while_a_linear_job_runs_is_409(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    release = asyncio.Event()

    class Blocking(FakeDataSource):
        async def fetch_teams(self) -> list[SourceTeam]:
            await release.wait()
            return []

    rules_app.dependency_overrides[get_delivery_data_source] = Blocking
    rules_app.dependency_overrides[get_datadog_source] = _source
    org_id = await _org(rules_client)
    await rules_client.post("/api/connectors/linear/sync", json={"organization_id": org_id})

    response = await rules_client.post(
        "/api/connectors/datadog/sync", json={"organization_id": org_id}
    )

    release.set()
    await settle(rules_app)
    assert response.status_code == 409
    assert "organization sync is running" in response.json()["detail"]


class _BlockingSource(InMemoryDatadogSource):
    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()

    async def fetch_codebases(self) -> list[SourceCodebase]:
        await self.release.wait()
        return []


async def test_linear_sync_while_a_datadog_job_runs_names_it_a_datadog_sync(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    blocking = _BlockingSource()
    rules_app.dependency_overrides[get_delivery_data_source] = FakeDataSource
    rules_app.dependency_overrides[get_datadog_source] = lambda: blocking
    org_id = await _org(rules_client)
    started = await rules_client.post(
        "/api/connectors/datadog/sync", json={"organization_id": org_id}
    )
    assert started.status_code == 202

    response = await rules_client.post(
        "/api/connectors/linear/sync", json={"organization_id": org_id}
    )
    status = (await rules_client.get("/api/connectors/datadog")).json()

    blocking.release.set()
    await settle(rules_app)
    assert response.status_code == 409
    assert response.json()["detail"].startswith("Another Datadog sync is running")
    assert status["running"]["kind"] == "datadog"
