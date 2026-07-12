from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_delivery_data_source
from app.domain.events.entities import EventType
from app.domain.sync.source import SourceEvent, SourceTeam, SourceWorkItem
from app.domain.work_items.entities import WorkItemType
from tests.fakes import FakeDataSource


def _fake_source() -> FakeDataSource:
    created = datetime.now(UTC) - timedelta(days=10)
    completed = datetime.now(UTC) - timedelta(days=2)
    return FakeDataSource(
        teams=[SourceTeam(external_id="lt1", name="Platform")],
        work_items=[
            SourceWorkItem(
                external_id="li1",
                title="Done item",
                type=WorkItemType.TASK,
                state="Done",
                team_external_id="lt1",
                project_external_id=None,
                created_at=created,
                completed_at=completed,
                events=(
                    SourceEvent(
                        external_id="li1:created",
                        type=EventType.CREATED,
                        occurred_at=created,
                    ),
                    SourceEvent(
                        external_id="li1:completed",
                        type=EventType.COMPLETED,
                        occurred_at=completed,
                    ),
                ),
            ),
            SourceWorkItem(
                external_id="li2",
                title="Open item",
                type=WorkItemType.TASK,
                state="Backlog",
                team_external_id="lt1",
                project_external_id=None,
                created_at=created,
            ),
        ],
    )


@pytest.fixture
def synced_team_id_factory(
    test_app: FastAPI, client: AsyncClient, settings_env: Callable[..., None]
) -> Callable[[], Awaitable[str]]:
    settings_env(linear_api_key="lin_api_test")
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source

    async def sync() -> str:
        org = (await client.post("/api/organizations", json={"name": "Acme"})).json()
        response = await client.post(
            "/api/connectors/linear/sync", json={"organization_id": org["id"]}
        )
        assert response.status_code == 200
        teams = (await client.get("/api/teams")).json()
        team_id: str = teams[0]["id"]
        return team_id

    return sync


async def test_sync_captures_daily_metric_snapshot(
    client: AsyncClient, synced_team_id_factory: Callable[[], Awaitable[str]]
) -> None:
    team_id = await synced_team_id_factory()

    response = await client.get(f"/api/metrics/snapshots?team_id={team_id}")

    assert response.status_code == 200
    snapshots = response.json()
    assert len(snapshots) == 1
    assert snapshots[0]["captured_on"] == datetime.now(UTC).date().isoformat()
    assert snapshots[0]["completed"] == 1
    assert snapshots[0]["window_days"] == 30
    assert snapshots[0]["blocked_seconds"] == 0.0


async def test_second_sync_same_day_does_not_duplicate_snapshots(
    client: AsyncClient, synced_team_id_factory: Callable[[], Awaitable[str]]
) -> None:
    team_id = await synced_team_id_factory()
    org = (await client.get("/api/organizations")).json()[0]
    second = await client.post(
        "/api/connectors/linear/sync", json={"organization_id": org["id"]}
    )
    assert second.status_code == 200

    response = await client.get(f"/api/metrics/snapshots?team_id={team_id}")

    assert len(response.json()) == 1


async def test_forecast_accuracy_reports_todays_snapshot_as_pending(
    client: AsyncClient, synced_team_id_factory: Callable[[], Awaitable[str]]
) -> None:
    team_id = await synced_team_id_factory()

    response = await client.get(f"/api/forecasts/accuracy?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "evaluated": 0,
        "pending": 1,
        "p50_hit_rate": None,
        "p85_hit_rate": None,
        "mean_abs_error_days": None,
    }


async def test_snapshots_require_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics/snapshots")).status_code == 422
    assert (await client.get("/api/forecasts/accuracy")).status_code == 422
