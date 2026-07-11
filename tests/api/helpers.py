"""Shared builders for API-level tests: create real parent chains via the API."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


async def create_team(client: AsyncClient) -> str:
    org = await client.post("/api/organizations", json={"name": "Acme"})
    assert org.status_code in (200, 201)
    team = await client.post(
        "/api/teams", json={"organization_id": org.json()["id"], "name": "Platform"}
    )
    assert team.status_code in (200, 201)
    team_id: str = team.json()["id"]
    return team_id


async def create_work_item(
    client: AsyncClient, *, team_id: str | None = None, title: str = "Ship it"
) -> str:
    if team_id is None:
        team_id = await create_team(client)
    response = await client.post(
        "/api/work-items", json={"team_id": team_id, "title": title}
    )
    assert response.status_code == 201
    work_item_id: str = response.json()["id"]
    return work_item_id


def days_ago(days: int) -> str:
    """ISO timestamp ``days`` days ago, pinned to 12:00 UTC (mid-bucket).

    API endpoints window against the server's wall clock, so tests must
    seed relative to now — but an event exactly N days ago sits on the
    same instant boundary the server buckets by. Anchoring mid-day keeps
    date-bucket assertions (history days, lead-time bins) 12 hours from
    any midnight flip between seeding and the request under test.
    """
    noon = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    return (noon - timedelta(days=days)).isoformat()
