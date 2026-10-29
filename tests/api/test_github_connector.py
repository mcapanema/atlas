import asyncio
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import GITHUB_NOT_CONFIGURED, get_code_host_source, get_delivery_data_source
from app.domain.sync.source import SourceCodebase, SourceTeam
from tests.api.helpers import settle
from tests.fakes import FakeDataSource, InMemoryCodeHostSource


def _code_source() -> InMemoryCodeHostSource:
    return InMemoryCodeHostSource(
        codebases=[
            SourceCodebase(external_id="r1", name="atlas", url="https://example.test/acme/atlas")
        ]
    )


@pytest.fixture
def github_configured(settings_env: Callable[..., None]) -> None:
    settings_env(github_token="ghp_test", github_owner="acme")


async def _org(client: AsyncClient) -> str:
    response = await client.post("/api/organizations", json={"name": "Acme"})
    assert response.status_code == 201
    org_id: str = response.json()["id"]
    return org_id


async def test_status_unconfigured_without_owner(
    settings_env: Callable[..., None], rules_client: AsyncClient
) -> None:
    settings_env(github_token="t", github_owner="")

    response = await rules_client.get("/api/connectors/github")

    assert response.status_code == 200
    assert response.json() == {"configured": False, "owner": None, "running": None}


async def test_status_reports_configured_with_owner(
    rules_client: AsyncClient, github_configured: None
) -> None:
    response = await rules_client.get("/api/connectors/github")

    assert response.json() == {"configured": True, "owner": "acme", "running": None}


async def test_sync_answers_409_until_configured(
    settings_env: Callable[..., None], rules_client: AsyncClient
) -> None:
    settings_env(github_token="", github_owner="acme")

    response = await rules_client.post("/api/connectors/github/sync", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == GITHUB_NOT_CONFIGURED


async def test_configured_source_is_the_github_adapter(github_configured: None) -> None:
    source = get_code_host_source()

    assert type(source).__name__ == "GitHubDataSource"


async def test_sync_runs_a_code_job_and_stores_codebases(
    rules_app: FastAPI, rules_client: AsyncClient, github_configured: None
) -> None:
    rules_app.dependency_overrides[get_code_host_source] = _code_source
    org_id = await _org(rules_client)

    response = await rules_client.post(
        "/api/connectors/github/sync", json={"organization_id": org_id}
    )

    assert response.status_code == 202
    assert response.json()["kind"] == "code"
    await settle(rules_app)
    job: dict[str, Any] = (
        await rules_client.get(f"/api/connectors/github/jobs/{response.json()['id']}")
    ).json()
    assert job["state"] == "succeeded"
    assert job["summary"] is None
    assert job["code_summary"] == {
        "codebases": 1,
        "pull_requests": 0,
        "deployments": 0,
        "events": 0,
    }
    codebases = (await rules_client.get(f"/api/codebases?organization_id={org_id}")).json()
    assert [(c["name"], c["team_id"]) for c in codebases] == [("atlas", None)]


async def test_sync_unknown_organization_answers_404(
    rules_app: FastAPI, rules_client: AsyncClient, github_configured: None
) -> None:
    rules_app.dependency_overrides[get_code_host_source] = _code_source

    response = await rules_client.post(
        "/api/connectors/github/sync", json={"organization_id": str(uuid4())}
    )

    assert response.status_code == 404


async def test_sync_without_organization_answers_422(
    rules_app: FastAPI, rules_client: AsyncClient, github_configured: None
) -> None:
    rules_app.dependency_overrides[get_code_host_source] = _code_source

    response = await rules_client.post("/api/connectors/github/sync", json={})

    assert response.status_code == 422
    assert "run a Linear sync first" in response.json()["detail"]


class _BlockingSource(FakeDataSource):
    """Holds the Linear sync inside fetch_teams until `release` is set."""

    def __init__(self) -> None:
        super().__init__(teams=[SourceTeam(external_id="lt1", name="Platform")])
        self.release = asyncio.Event()

    async def fetch_teams(self) -> list[SourceTeam]:
        await self.release.wait()
        return await super().fetch_teams()


async def test_sync_while_linear_job_runs_answers_409(
    rules_app: FastAPI,
    rules_client: AsyncClient,
    settings_env: Callable[..., None],
) -> None:
    settings_env(linear_api_key="lin_api_test", github_token="ghp_test", github_owner="acme")
    linear = _BlockingSource()
    rules_app.dependency_overrides[get_delivery_data_source] = lambda: linear
    rules_app.dependency_overrides[get_code_host_source] = _code_source
    org_id = await _org(rules_client)
    started = await rules_client.post(
        "/api/connectors/linear/sync", json={"organization_id": org_id}
    )
    assert started.status_code == 202

    response = await rules_client.post(
        "/api/connectors/github/sync", json={"organization_id": org_id}
    )
    status = (await rules_client.get("/api/connectors/github")).json()

    linear.release.set()
    await settle(rules_app)
    assert response.status_code == 409
    assert "organization sync is running" in response.json()["detail"]
    assert status["running"]["kind"] == "organization"


async def test_unknown_job_answers_404(rules_client: AsyncClient) -> None:
    response = await rules_client.get(f"/api/connectors/github/jobs/{uuid4()}")

    assert response.status_code == 404
    assert "Atlas may have restarted" in response.json()["detail"]
