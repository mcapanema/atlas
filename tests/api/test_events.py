from uuid import uuid4

from httpx import AsyncClient


async def test_list_events_empty(client: AsyncClient) -> None:
    response = await client.get("/api/events", params={"work_item_id": str(uuid4())})

    assert response.status_code == 200
    assert response.json() == []


async def test_list_requires_work_item_id(client: AsyncClient) -> None:
    response = await client.get("/api/events")

    assert response.status_code == 422


async def test_record_then_list_event(client: AsyncClient) -> None:
    work_item_id = str(uuid4())
    create = await client.post(
        "/api/events",
        json={
            "work_item_id": work_item_id,
            "type": "state_changed",
            "occurred_at": "2026-01-01T00:00:00Z",
            "from_state": "backlog",
            "to_state": "in_progress",
        },
    )

    assert create.status_code == 201
    body = create.json()
    assert body["type"] == "state_changed"
    assert body["to_state"] == "in_progress"

    listed = await client.get("/api/events", params={"work_item_id": work_item_id})
    assert [e["type"] for e in listed.json()] == ["state_changed"]


async def test_record_rejects_unknown_type(client: AsyncClient) -> None:
    response = await client.post(
        "/api/events",
        json={
            "work_item_id": str(uuid4()),
            "type": "exploded",
            "occurred_at": "2026-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 422


async def test_record_rejects_timezone_naive_occurred_at(client: AsyncClient) -> None:
    """Pydantic accepts a tz-naive datetime; Event.__post_init__ then raises
    ValueError, which the app-wide handler must turn into 422, not a 500."""
    response = await client.post(
        "/api/events",
        json={
            "work_item_id": str(uuid4()),
            "type": "state_changed",
            "occurred_at": "2026-01-01T00:00:00",
            "from_state": "backlog",
            "to_state": "in_progress",
        },
    )

    assert response.status_code == 422
