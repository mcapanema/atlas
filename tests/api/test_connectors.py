from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_delivery_data_source
from app.domain.events.entities import EventType
from app.domain.sync.port import DataSourceError
from app.domain.sync.source import SourceEvent, SourceProject, SourceTeam, SourceWorkItem
from app.domain.work_items.entities import WorkItemType
from tests.fakes import FakeDataSource


def _fake_source() -> FakeDataSource:
    occurred = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    return FakeDataSource(
        teams=[SourceTeam(external_id="lt1", name="Platform")],
        projects=[SourceProject(external_id="lp1", name="Q3 Launch", team_external_id="lt1")],
        work_items=[
            SourceWorkItem(
                external_id="li1",
                title="Fix login",
                type=WorkItemType.TASK,
                state="In Progress",
                team_external_id="lt1",
                project_external_id="lp1",
                created_at=occurred,
                events=(
                    SourceEvent(
                        external_id="li1:created",
                        type=EventType.CREATED,
                        occurred_at=occurred,
                    ),
                ),
            )
        ],
    )


@pytest.fixture
def linear_configured(settings_env: Callable[..., None]) -> None:
    settings_env(linear_api_key="lin_api_test")


@pytest.fixture
def linear_unconfigured(settings_env: Callable[..., None]) -> None:
    settings_env(linear_api_key="")


async def test_status_reports_unconfigured(
    client: AsyncClient, linear_unconfigured: None
) -> None:
    response = await client.get("/api/connectors/linear")

    assert response.status_code == 200
    assert response.json() == {"configured": False}


async def test_status_reports_configured(
    client: AsyncClient, linear_configured: None
) -> None:
    response = await client.get("/api/connectors/linear")

    assert response.status_code == 200
    assert response.json() == {"configured": True}


async def test_sync_returns_409_when_unconfigured(
    client: AsyncClient, linear_unconfigured: None
) -> None:
    response = await client.post(
        "/api/connectors/linear/sync", json={"organization_id": str(uuid4())}
    )

    assert response.status_code == 409


async def test_sync_pulls_source_into_domain_and_is_idempotent(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source
    org = (await client.post("/api/organizations", json={"name": "Acme"})).json()

    first = await client.post(
        "/api/connectors/linear/sync", json={"organization_id": org["id"]}
    )

    assert first.status_code == 200
    assert first.json() == {
        "teams": 1,
        "projects": 1,
        "work_items": 1,
        "events": 1,
        "divergences": 0,
    }
    teams = (await client.get("/api/teams")).json()
    assert teams[0]["external_id"] == "lt1"

    second = await client.post(
        "/api/connectors/linear/sync", json={"organization_id": org["id"]}
    )

    assert second.json() == {
        "teams": 0,
        "projects": 0,
        "work_items": 0,
        "events": 0,
        "divergences": 0,
    }


async def test_sync_unknown_organization_is_404(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source

    response = await client.post(
        "/api/connectors/linear/sync", json={"organization_id": str(uuid4())}
    )

    assert response.status_code == 404


class FailingDataSource:
    async def fetch_teams(self) -> list[SourceTeam]:
        raise DataSourceError("Linear API returned HTTP 500")

    async def fetch_projects(self) -> list[SourceProject]:
        return []

    async def fetch_work_items(self) -> list[SourceWorkItem]:
        return []


async def test_sync_returns_502_when_source_fails(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = FailingDataSource
    org = (await client.post("/api/organizations", json={"name": "Acme"})).json()

    response = await client.post(
        "/api/connectors/linear/sync", json={"organization_id": org["id"]}
    )

    assert response.status_code == 502
    assert "Linear API returned HTTP 500" in response.json()["detail"]


async def test_sync_without_organization_bootstraps_from_source(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source

    response = await client.post("/api/connectors/linear/sync", json={})

    assert response.status_code == 200
    orgs = (await client.get("/api/organizations")).json()
    assert [org["name"] for org in orgs] == ["Acme Workspace"]
    teams = (await client.get("/api/teams")).json()
    assert teams[0]["external_id"] == "lt1"


async def test_sync_without_organization_is_422_when_ambiguous(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source
    await client.post("/api/organizations", json={"name": "A"})
    await client.post("/api/organizations", json={"name": "B"})

    response = await client.post("/api/connectors/linear/sync", json={})

    assert response.status_code == 422
