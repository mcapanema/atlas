from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_delivery_data_source
from app.config import get_settings
from app.domain.events.entities import EventType
from app.domain.sync.source import SourceEvent, SourceProject, SourceTeam, SourceWorkItem
from app.domain.work_items.entities import WorkItemType


class FakeDataSource:
    async def fetch_teams(self) -> list[SourceTeam]:
        return [SourceTeam(external_id="lt1", name="Platform")]

    async def fetch_projects(self) -> list[SourceProject]:
        return [SourceProject(external_id="lp1", name="Q3 Launch", team_external_id="lt1")]

    async def fetch_work_items(self) -> list[SourceWorkItem]:
        occurred = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
        return [
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
        ]


# get_settings is lru_cached; clear around each env change so the request
# under test re-reads the environment (and clear again on teardown so later
# tests aren't poisoned). monkeypatch undoes the env var itself.
@pytest.fixture
def linear_configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ATLAS_LINEAR_API_KEY", "lin_api_test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# Empty string (falsy) rather than delenv: a real env var always beats .env,
# so this stays hermetic even when the developer's .env sets a key.
@pytest.fixture
def linear_unconfigured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ATLAS_LINEAR_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
    test_app.dependency_overrides[get_delivery_data_source] = FakeDataSource
    org = (await client.post("/api/organizations", json={"name": "Acme"})).json()

    first = await client.post(
        "/api/connectors/linear/sync", json={"organization_id": org["id"]}
    )

    assert first.status_code == 200
    assert first.json() == {"teams": 1, "projects": 1, "work_items": 1, "events": 1}
    teams = (await client.get("/api/teams")).json()
    assert teams[0]["external_id"] == "lt1"

    second = await client.post(
        "/api/connectors/linear/sync", json={"organization_id": org["id"]}
    )

    assert second.json() == {"teams": 0, "projects": 0, "work_items": 0, "events": 0}


async def test_sync_unknown_organization_is_422(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = FakeDataSource

    response = await client.post(
        "/api/connectors/linear/sync", json={"organization_id": str(uuid4())}
    )

    assert response.status_code == 422
