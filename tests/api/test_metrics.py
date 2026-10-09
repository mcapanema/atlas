from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.metrics import Period
from app.application.scope import ScopeData, ScopeSampleLoader
from app.domain.snapshots.entities import ForecastSnapshot
from app.infrastructure.repositories.snapshots import SqlAlchemyForecastSnapshotRepository
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository
from tests.api.helpers import create_team, days_ago


async def test_team_flow_metrics_end_to_end(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})).json()
    for type_, days in (("created", 10), ("started", 6), ("completed", 2)):
        response = await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": type_,
                "occurred_at": days_ago(days),
            },
        )
        assert response.status_code == 201

    response = await client.get(f"/api/metrics?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["completed"] == 1
    assert body["wip"] == 0
    assert body["lead_time"]["p50_seconds"] == pytest.approx(8 * 86400)
    assert body["cycle_time"]["p50_seconds"] == pytest.approx(4 * 86400)
    assert body["blocked_seconds"] == 0
    assert body["flow_efficiency"] == 1.0


async def test_metrics_for_unknown_team_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics?team_id={uuid4()}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


async def test_metrics_for_unknown_project_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics?project_id={uuid4()}")

    assert response.status_code == 404


async def test_flow_history_for_unknown_team_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics/history?team_id={uuid4()}")

    assert response.status_code == 404


async def test_window_days_is_validated(client: AsyncClient) -> None:
    team_id = await create_team(client)
    response = await client.get(f"/api/metrics?team_id={team_id}&window_days=0")
    assert response.status_code == 422
    assert (await client.get("/api/metrics")).status_code == 422  # a scope is required


async def test_metrics_scoped_by_project(client: AsyncClient) -> None:
    team_id = await create_team(client)
    project = (
        await client.post("/api/projects", json={"team_id": team_id, "name": "Apollo"})
    ).json()
    for title, project_id in (("In project", project["id"]), ("Outside", None)):
        item = (
            await client.post(
                "/api/work-items",
                json={"team_id": team_id, "title": title, "project_id": project_id},
            )
        ).json()
        await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": "created",
                "occurred_at": days_ago(2),
            },
        )
        await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": "completed",
                "occurred_at": days_ago(1),
            },
        )

    response = await client.get(f"/api/metrics?project_id={project['id']}")

    assert response.status_code == 200
    assert response.json()["completed"] == 1


async def test_metrics_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics")).status_code == 422
    assert (
        await client.get(f"/api/metrics?team_id={uuid4()}&project_id={uuid4()}")
    ).status_code == 422


async def test_flow_history_end_to_end(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})).json()
    for type_, days in (("created", 10), ("started", 6), ("completed", 2)):
        await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": type_,
                "occurred_at": days_ago(days),
            },
        )

    response = await client.get(f"/api/metrics/history?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["days"]) == 91  # default 90-day window, inclusive
    assert body["days"][-1]["done"] == 1
    assert body["days"][-1]["in_progress"] == 0
    assert body["bucket_days"] == 7
    assert len(body["buckets"]) == 13  # ceil(90 / 7)
    assert sum(b["completed"] for b in body["buckets"]) == 1


async def test_flow_history_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics/history")).status_code == 422
    assert (
        await client.get(f"/api/metrics/history?team_id={uuid4()}&project_id={uuid4()}")
    ).status_code == 422


async def test_lead_time_distribution_end_to_end(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})).json()
    for type_, days in (("created", 10), ("completed", 2)):
        await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": type_,
                "occurred_at": days_ago(days),
            },
        )

    response = await client.get(f"/api/metrics/lead-time-distribution?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["bins"]) == 9  # bins for days 0..8
    assert body["bins"][8] == {"start_days": 8, "end_days": 9, "count": 1}
    assert sum(b["count"] for b in body["bins"]) == 1
    # One item: every percentile is its own lead time.
    assert body["p50_seconds"] == pytest.approx(8 * 86400)
    assert body["p85_seconds"] == pytest.approx(8 * 86400)


async def test_lead_time_distribution_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics/lead-time-distribution")).status_code == 422
    assert (
        await client.get(
            f"/api/metrics/lead-time-distribution?team_id={uuid4()}&project_id={uuid4()}"
        )
    ).status_code == 422


async def test_flow_metrics_include_queue_and_touch_time(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})).json()
    for type_, days in (("created", 10), ("started", 6), ("completed", 2)):
        await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": type_, "occurred_at": days_ago(days)},
        )

    body = (await client.get(f"/api/metrics?team_id={team_id}")).json()

    assert body["queue_time"]["p50_seconds"] == pytest.approx(4 * 86400)
    assert body["touch_time"]["p50_seconds"] == pytest.approx(4 * 86400)


async def test_aging_wip_end_to_end(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Stuck"})
    ).json()
    for type_, days in (("created", 10), ("started", 6)):
        await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": type_, "occurred_at": days_ago(days)},
        )

    response = await client.get(f"/api/metrics/aging-wip?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["cycle_time_percentile_seconds"] is None
    (aging_item,) = body["items"]
    assert aging_item["title"] == "Stuck"
    assert aging_item["assignee"] is None  # created via REST: no source assignee
    assert aging_item["over_percentile"] is False
    assert aging_item["age_seconds"] > 5 * 86400


async def test_aging_wip_shows_the_stored_assignee(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Owned"})
    ).json()
    await client.post(
        "/api/events",
        json={"work_item_id": item["id"], "type": "started", "occurred_at": days_ago(3)},
    )
    async with sessionmaker() as session:  # only sync sets it: no REST field to write
        repo = SqlAlchemyWorkItemRepository(session)
        stored = await repo.get(UUID(item["id"]))
        assert stored is not None
        await repo.update(replace(stored, assignee="Ada Lovelace"))
        await session.commit()

    body = (await client.get(f"/api/metrics/aging-wip?team_id={team_id}")).json()

    assert [i["assignee"] for i in body["items"]] == ["Ada Lovelace"]


async def test_aging_wip_for_unknown_team_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics/aging-wip?team_id={uuid4()}")
    assert response.status_code == 404


async def test_aging_wip_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics/aging-wip")).status_code == 422


async def test_delivery_health_end_to_end(client: AsyncClient) -> None:
    team_id = await create_team(client)
    for title in ("Ship", "Ship again", "Ship more", "Ship four", "Ship five"):
        item = (
            await client.post("/api/work-items", json={"team_id": team_id, "title": title})
        ).json()
        for type_, days in (("created", 10), ("started", 6), ("completed", 2)):
            await client.post(
                "/api/events",
                json={"work_item_id": item["id"], "type": type_, "occurred_at": days_ago(days)},
            )
    for title in ("Shipped", "Shipped again", "Shipped more", "Shipped four", "Shipped five"):
        item = (
            await client.post("/api/work-items", json={"team_id": team_id, "title": title})
        ).json()
        for type_, days in (("created", 60), ("started", 45), ("completed", 40)):
            await client.post(
                "/api/events",
                json={"work_item_id": item["id"], "type": type_, "occurred_at": days_ago(days)},
            )

    response = await client.get(f"/api/metrics/health?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["score"] <= 100
    assert body["band"] in ("healthy", "warning", "critical")
    assert "predictability" in [c["name"] for c in body["components"]]
    assert all(c["band"] in ("healthy", "warning", "critical") for c in body["components"])


async def test_delivery_health_for_unknown_team_is_404(client: AsyncClient) -> None:
    assert (await client.get(f"/api/metrics/health?team_id={uuid4()}")).status_code == 404


async def test_delivery_health_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics/health")).status_code == 422


async def _seed_completed(
    client: AsyncClient, team_id: str, *, title: str, type_: str = "task", state: str = "done"
) -> None:
    item = (
        await client.post(
            "/api/work-items",
            json={"team_id": team_id, "title": title, "type": type_, "state": state},
        )
    ).json()
    for event_type, days in (("created", 10), ("completed", 2)):
        response = await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": event_type, "occurred_at": days_ago(days)},
        )
        assert response.status_code == 201


async def test_metrics_types_filter(client: AsyncClient) -> None:
    team_id = await create_team(client)
    await _seed_completed(client, team_id, title="Feature", type_="story")
    await _seed_completed(client, team_id, title="Chore", type_="task")

    unfiltered = await client.get(f"/api/metrics?team_id={team_id}")
    filtered = await client.get(f"/api/metrics?team_id={team_id}&types=story")

    assert unfiltered.json()["completed"] == 2
    assert filtered.json()["completed"] == 1


async def test_metrics_exclude_states_filter(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (
        await client.post(
            "/api/work-items",
            json={"team_id": team_id, "title": "Junk", "state": "Canceled"},
        )
    ).json()
    for event_type, days in (("created", 100), ("started", 99)):
        await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": event_type, "occurred_at": days_ago(days)},
        )

    unfiltered = await client.get(f"/api/metrics?team_id={team_id}")
    filtered = await client.get(f"/api/metrics?team_id={team_id}&exclude_states=canceled")

    assert unfiltered.json()["wip"] == 1  # the junk item pollutes WIP today
    assert filtered.json()["wip"] == 0


async def test_aging_wip_honors_item_filters(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (
        await client.post(
            "/api/work-items",
            json={"team_id": team_id, "title": "Zombie", "state": "Canceled"},
        )
    ).json()
    for event_type, days in (("created", 50), ("started", 49)):
        await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": event_type, "occurred_at": days_ago(days)},
        )

    response = await client.get(f"/api/metrics/aging-wip?team_id={team_id}&exclude_states=canceled")

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_metrics_rejects_unknown_type(client: AsyncClient) -> None:
    team_id = await create_team(client)
    response = await client.get(f"/api/metrics?team_id={team_id}&types=epic")
    assert response.status_code == 422


async def test_metrics_explicit_period(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Old but real"})
    ).json()
    for event_type, days in (("created", 45), ("completed", 40)):
        await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": event_type, "occurred_at": days_ago(days)},
        )
    start, end = days_ago(50)[:10], days_ago(35)[:10]

    default = await client.get(f"/api/metrics?team_id={team_id}")
    period = await client.get(f"/api/metrics?team_id={team_id}&start={start}&end={end}")

    assert default.json()["completed"] == 0  # outside the default 30d window
    body = period.json()
    assert body["completed"] == 1
    assert body["window_start"][:10] == start


async def test_metrics_period_requires_both_bounds(client: AsyncClient) -> None:
    team_id = await create_team(client)
    response = await client.get(f"/api/metrics?team_id={team_id}&start=2026-06-01")
    assert response.status_code == 422
    assert "both" in response.json()["detail"]


async def test_metrics_period_rejects_inverted_range(client: AsyncClient) -> None:
    team_id = await create_team(client)
    response = await client.get(f"/api/metrics?team_id={team_id}&start=2026-06-10&end=2026-06-01")
    assert response.status_code == 422


async def test_metrics_period_rejects_range_over_365_days(client: AsyncClient) -> None:
    team_id = await create_team(client)
    response = await client.get(f"/api/metrics?team_id={team_id}&start=2020-01-01&end=2021-01-02")
    assert response.status_code == 422


async def test_history_honors_explicit_period(client: AsyncClient) -> None:
    team_id = await create_team(client)
    start, end = days_ago(50)[:10], days_ago(35)[:10]

    response = await client.get(f"/api/metrics/history?team_id={team_id}&start={start}&end={end}")

    assert response.status_code == 200
    assert response.json()["window_start"][:10] == start


async def test_flow_history_reports_data_as_of(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})).json()
    await client.post(
        "/api/events",
        json={
            "work_item_id": item["id"],
            "type": "created",
            "occurred_at": days_ago(3),
        },
    )
    await client.post(
        "/api/events",
        json={
            "work_item_id": item["id"],
            "type": "completed",
            "occurred_at": days_ago(2),
        },
    )

    body = (await client.get(f"/api/metrics/history?team_id={team_id}")).json()

    # recorded_at is stamped at ingest, so it is ~now regardless of occurred_at.
    assert body["data_as_of"] is not None
    assert body["data_as_of"].startswith(datetime.now(UTC).strftime("%Y-%m-%d"))


async def test_flow_history_data_as_of_is_null_for_an_empty_team(
    client: AsyncClient,
) -> None:
    team_id = await create_team(client)

    body = (await client.get(f"/api/metrics/history?team_id={team_id}")).json()

    assert body["data_as_of"] is None


async def test_flow_history_buckets_a_short_window_daily(client: AsyncClient) -> None:
    team_id = await create_team(client)

    response = await client.get(f"/api/metrics/history?team_id={team_id}&window_days=7")

    assert response.status_code == 200
    body = response.json()
    assert body["bucket_days"] == 1
    assert len(body["buckets"]) == 7


def test_period_days_is_inclusive_and_zero_when_open() -> None:
    assert Period(start=date(2026, 6, 1), end=date(2026, 6, 30)).days == 30
    assert Period().days == 0


async def _parked_then_restarted(client: AsyncClient, items: int = 1) -> str:
    """`items` items, each started 30d ago, moved back 25d ago, restarted 2d ago."""
    team_id = await create_team(client)
    for _ in range(items):
        item = (
            await client.post("/api/work-items", json={"team_id": team_id, "title": "Parked"})
        ).json()
        for event_type, days in (("created", 40), ("started", 30), ("stopped", 25), ("started", 2)):
            response = await client.post(
                "/api/events",
                json={
                    "work_item_id": item["id"],
                    "type": event_type,
                    "occurred_at": days_ago(days),
                },
            )
            assert response.status_code == 201
    return team_id


async def test_explicit_period_measures_wip_as_it_stood_at_the_range_end(
    client: AsyncClient,
) -> None:
    team_id = await _parked_then_restarted(client)
    start, end = days_ago(22)[:10], days_ago(15)[:10]

    now = await client.get(f"/api/metrics?team_id={team_id}")
    past = await client.get(f"/api/metrics?team_id={team_id}&start={start}&end={end}")

    assert now.json()["wip"] == 1  # restarted two days ago
    assert past.json()["wip"] == 0  # parked (moved back) throughout the range


async def test_a_period_ending_today_matches_the_trailing_window(client: AsyncClient) -> None:
    team_id = await _parked_then_restarted(client)
    start, end = days_ago(29)[:10], days_ago(0)[:10]

    default = await client.get(f"/api/metrics?team_id={team_id}")
    ranged = await client.get(f"/api/metrics?team_id={team_id}&start={start}&end={end}")

    assert ranged.json()["wip"] == default.json()["wip"] == 1


async def _completed_then_reopened(client: AsyncClient) -> str:
    """Completed 20d ago, reopened (started again) 2d ago — not done today."""
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Reopened"})
    ).json()
    for event_type, days in (("created", 40), ("started", 30), ("completed", 20), ("started", 2)):
        response = await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": event_type, "occurred_at": days_ago(days)},
        )
        assert response.status_code == 201
    return team_id


async def test_explicit_period_history_and_distribution_count_completions_as_they_stood(
    client: AsyncClient,
) -> None:
    team_id = await _completed_then_reopened(client)
    period = f"team_id={team_id}&start={days_ago(25)[:10]}&end={days_ago(15)[:10]}"

    history = (await client.get(f"/api/metrics/history?{period}")).json()
    distribution = (await client.get(f"/api/metrics/lead-time-distribution?{period}")).json()

    # Done throughout the range; the later reopen must not erase that completion.
    assert sum(bucket["completed"] for bucket in history["buckets"]) == 1
    assert sum(bin_["count"] for bin_ in distribution["bins"]) == 1


async def test_explicit_period_health_reads_wip_as_it_stood(client: AsyncClient) -> None:
    team_id = await _parked_then_restarted(client, items=5)
    period = f"team_id={team_id}&start={days_ago(22)[:10]}&end={days_ago(15)[:10]}"

    ranged = (await client.get(f"/api/metrics/health?{period}")).json()
    now = (await client.get(f"/api/metrics/health?team_id={team_id}")).json()

    # The risk component exists only while enough items are in progress at the
    # window's end: parked throughout the range, in progress again today.
    assert "risk" not in {component["name"] for component in ranged["components"]}
    assert "risk" in {component["name"] for component in now["components"]}


async def _seed_overview_team(client: AsyncClient) -> str:
    """A done task, an in-progress task, and a started item sitting in a "Canceled" state."""
    team_id = await create_team(client)
    for title, state, history in (
        ("Shipped", "Done", (("created", 20), ("started", 12), ("completed", 3))),
        ("Doing", "In Progress", (("created", 9), ("started", 5))),
        ("Dropped", "Canceled", (("created", 15), ("started", 14))),
    ):
        item = (
            await client.post(
                "/api/work-items", json={"team_id": team_id, "title": title, "state": state}
            )
        ).json()
        for type_, days in history:
            response = await client.post(
                "/api/events",
                json={"work_item_id": item["id"], "type": type_, "occurred_at": days_ago(days)},
            )
            assert response.status_code == 201
    return team_id


@pytest.mark.parametrize(
    "extra",
    # window_days is left out: an explicit period overrides it, so it is
    # covered without one in test_overview_honors_window_days_without_a_period.
    ["", "&exclude_states=canceled", "&types=bug"],
)
async def test_overview_matches_the_standalone_endpoints(client: AsyncClient, extra: str) -> None:
    team_id = await _seed_overview_team(client)
    # An explicit period pins `now`, so window bounds compare exactly.
    end = datetime.now(UTC).date()
    start = end - timedelta(days=29)
    query = f"team_id={team_id}&start={start}&end={end}{extra}"

    response = await client.get(f"/api/metrics/overview?{query}")

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"] == (await client.get(f"/api/metrics?{query}")).json()
    assert body["health"] == (await client.get(f"/api/metrics/health?{query}")).json()
    assert (
        body["accuracy"] == (await client.get(f"/api/forecasts/accuracy?team_id={team_id}")).json()
    )
    assert (
        body["snapshots"] == (await client.get(f"/api/metrics/snapshots?team_id={team_id}")).json()
    )


async def test_overview_defaults_to_the_trailing_30_days(client: AsyncClient) -> None:
    team_id = await _seed_overview_team(client)

    body = (await client.get(f"/api/metrics/overview?team_id={team_id}")).json()

    metrics = body["metrics"]
    window = datetime.fromisoformat(metrics["window_end"]) - datetime.fromisoformat(
        metrics["window_start"]
    )
    assert window == timedelta(days=30)
    assert metrics["completed"] == 1
    health_window = datetime.fromisoformat(body["health"]["window_end"]) - datetime.fromisoformat(
        body["health"]["window_start"]
    )
    assert health_window == timedelta(days=30)


async def test_overview_honors_window_days_without_a_period(client: AsyncClient) -> None:
    team_id = await _seed_overview_team(client)
    # Completed 60 days ago: outside the default 30-day window, inside 90.
    item = (await client.post("/api/work-items", json={"team_id": team_id, "title": "Old"})).json()
    for type_, days in (("created", 70), ("started", 65), ("completed", 60)):
        response = await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": type_, "occurred_at": days_ago(days)},
        )
        assert response.status_code == 201

    body = (await client.get(f"/api/metrics/overview?team_id={team_id}&window_days=90")).json()

    for part in ("metrics", "health"):
        window = datetime.fromisoformat(body[part]["window_end"]) - datetime.fromisoformat(
            body[part]["window_start"]
        )
        assert window == timedelta(days=90), part
    assert body["metrics"]["completed"] == 2
    standalone = (await client.get(f"/api/metrics?team_id={team_id}&window_days=90")).json()
    assert body["metrics"]["completed"] == standalone["completed"]


async def test_overview_loads_the_scope_once(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    team_id = await _seed_overview_team(client)
    loads = 0
    original = ScopeSampleLoader.load_data

    async def counting(self: ScopeSampleLoader, **kwargs: Any) -> ScopeData:
        nonlocal loads
        loads += 1
        return await original(self, **kwargs)

    monkeypatch.setattr(ScopeSampleLoader, "load_data", counting)

    response = await client.get(f"/api/metrics/overview?team_id={team_id}&exclude_states=canceled")

    assert response.status_code == 200
    assert loads == 1


async def test_overview_scores_accuracy_against_unfiltered_completions(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    team_id = await _seed_overview_team(client)
    # A forecast 10 days ago for 1 remaining item; "Shipped" (a task) completed
    # 3 days ago resolves it. A `types=bug` view has no completions at all.
    async with sessionmaker() as session:
        await SqlAlchemyForecastSnapshotRepository(session).add(
            ForecastSnapshot(
                captured_on=(datetime.now(UTC) - timedelta(days=10)).date(),
                window_days=90,
                remaining=1,
                p50_days=30,
                p85_days=30,
                team_id=UUID(team_id),
                created_at=datetime.now(UTC) - timedelta(days=10),
            )
        )
        await session.commit()

    body = (await client.get(f"/api/metrics/overview?team_id={team_id}&types=bug")).json()

    assert body["metrics"]["completed"] == 0
    assert body["accuracy"]["evaluated"] == 1
    assert body["accuracy"]["p85_hit_rate"] == 1.0


async def test_overview_for_an_empty_team_is_empty_not_an_error(client: AsyncClient) -> None:
    team_id = await create_team(client)

    response = await client.get(f"/api/metrics/overview?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["completed"] == 0
    assert body["metrics"]["lead_time"] is None
    assert body["accuracy"]["evaluated"] == 0
    assert body["snapshots"] == []


async def test_overview_for_unknown_team_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics/overview?team_id={uuid4()}")

    assert response.status_code == 404


async def test_overview_window_days_floors_at_health_minimum(client: AsyncClient) -> None:
    team_id = await create_team(client)

    response = await client.get(f"/api/metrics/overview?team_id={team_id}&window_days=6")

    assert response.status_code == 422
