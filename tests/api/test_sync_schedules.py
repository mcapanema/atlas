from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

SCHEDULE: dict[str, Any] = {
    "enabled": True,
    "days": [5, 1, 3, 1],
    "window_start": "08:00",
    "window_end": "18:00",
    "interval_minutes": 120,
    "timezone": "America/Sao_Paulo",
}


async def _org(client: AsyncClient) -> str:
    response = await client.post("/api/organizations", json={"name": "Acme"})
    assert response.status_code == 201
    return str(response.json()["id"])


def _url(organization_id: object) -> str:
    return f"/api/organizations/{organization_id}/sync-schedule"


async def test_unknown_organization_is_404(client: AsyncClient) -> None:
    assert (await client.get(_url(uuid4()))).status_code == 404
    assert (await client.put(_url(uuid4()), json=SCHEDULE)).status_code == 404


async def test_no_schedule_reads_as_null(client: AsyncClient) -> None:
    response = await client.get(_url(await _org(client)))

    assert response.status_code == 200
    assert response.json() is None


async def test_put_saves_and_get_reads_it_back(client: AsyncClient) -> None:
    org_id = await _org(client)

    saved = await client.put(_url(org_id), json=SCHEDULE)

    assert saved.status_code == 200
    body = saved.json()
    assert body["enabled"] is True
    assert body["days"] == [1, 3, 5]
    assert body["window_start"] == "08:00:00"
    assert body["window_end"] == "18:00:00"
    assert body["interval_minutes"] == 120
    assert body["timezone"] == "America/Sao_Paulo"
    assert body["last_run"] is None
    assert body["next_run_at"] is not None
    assert (await client.get(_url(org_id))).json() == body


async def test_disabled_schedule_has_no_next_run(client: AsyncClient) -> None:
    org_id = await _org(client)

    body = (await client.put(_url(org_id), json={**SCHEDULE, "enabled": False})).json()

    assert body["enabled"] is False
    assert body["next_run_at"] is None


@pytest.mark.parametrize(
    ("change", "detail"),
    [
        ({"timezone": "Mars/Base"}, "Unknown timezone"),
        ({"days": []}, "at least one day"),
        ({"days": [0]}, "ISO weekdays"),
        ({"window_start": "22:00", "window_end": "02:00"}, "overnight"),
        ({"interval_minutes": 5}, "between 15 and 1440"),
    ],
)
async def test_invalid_schedule_is_422_with_the_reason(
    client: AsyncClient, change: dict[str, Any], detail: str
) -> None:
    response = await client.put(_url(await _org(client)), json={**SCHEDULE, **change})

    assert response.status_code == 422
    assert detail in response.json()["detail"]
