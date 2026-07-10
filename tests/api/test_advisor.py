from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_advisor_port
from app.config import Settings
from app.domain.advisor.entities import DeliveryAdvice, Recommendation
from app.domain.advisor.port import DeliveryContext


class FakeAdvisor:
    async def advise(self, context: DeliveryContext) -> DeliveryAdvice:
        return DeliveryAdvice(
            generated_at=datetime(2026, 7, 10, tzinfo=UTC),
            summary="Flow is healthy.",
            recommendations=[
                Recommendation(
                    title="Lower WIP",
                    priority="high",
                    problem="WIP is 12 while weekly throughput is 3",
                    root_cause="Work is started faster than it finishes",
                    action="Set a WIP limit of 6",
                    evidence=["wip=12", "completed=3"],
                )
            ],
        )


async def _create_team(client: AsyncClient) -> str:
    org = await client.post("/api/organizations", json={"name": "Acme"})
    team = await client.post(
        "/api/teams", json={"organization_id": org.json()["id"], "name": "Platform"}
    )
    assert team.status_code in (200, 201)
    team_id: str = team.json()["id"]
    return team_id


async def test_status_reports_unconfigured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.advisor.get_settings", lambda: Settings(openrouter_api_key=None)
    )
    response = await client.get("/api/recommendations/status")
    assert response.status_code == 200
    assert response.json() == {"configured": False}


async def test_status_reports_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.advisor.get_settings", lambda: Settings(openrouter_api_key="sk-test")
    )
    response = await client.get("/api/recommendations/status")
    assert response.json() == {"configured": True}


async def test_recommendations_409_when_unconfigured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings", lambda: Settings(openrouter_api_key=None)
    )
    response = await client.get(f"/api/recommendations?team_id={uuid4()}")
    assert response.status_code == 409


async def test_recommendations_requires_exactly_one_scope(
    client: AsyncClient, test_app: FastAPI
) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeAdvisor()
    response = await client.get("/api/recommendations")
    assert response.status_code == 422


async def test_recommendations_happy_path(client: AsyncClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_advisor_port] = lambda: FakeAdvisor()
    team_id = await _create_team(client)

    response = await client.get(f"/api/recommendations?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Flow is healthy."
    assert body["recommendations"][0]["title"] == "Lower WIP"
    assert body["recommendations"][0]["priority"] == "high"
    assert body["recommendations"][0]["root_cause"].startswith("Work is started")
    assert body["recommendations"][0]["evidence"] == ["wip=12", "completed=3"]
