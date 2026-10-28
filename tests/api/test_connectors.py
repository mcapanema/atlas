import asyncio
import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from app.api.deps import get_delivery_data_source
from app.api.recompute import RecomputeRunner
from app.api.sync_jobs import SyncJobRunner
from app.domain.events.entities import EventType
from app.domain.sync.port import DataSourceError
from app.domain.sync.source import (
    SourceEvent,
    SourcePerson,
    SourceProject,
    SourceTeam,
    SourceWorkItem,
)
from app.domain.work_items.entities import WorkItemType
from tests.api.helpers import create_org_and_team, settle
from tests.fakes import FakeDataSource


def _fake_source() -> FakeDataSource:
    occurred = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    return FakeDataSource(
        teams=[SourceTeam(external_id="lt1", name="Platform")],
        projects=[SourceProject(external_id="lp1", name="Q3 Launch", team_external_ids=("lt1",))],
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


class _BlockingSource(FakeDataSource):
    """Holds the sync inside fetch_teams until `release` is set."""

    def __init__(self) -> None:
        super().__init__(teams=[SourceTeam(external_id="lt1", name="Platform")])
        self.release = asyncio.Event()

    async def fetch_teams(self) -> list[SourceTeam]:
        await self.release.wait()
        return await super().fetch_teams()


async def _outcome(app: FastAPI, client: AsyncClient, response: Response) -> dict[str, Any]:
    """The finished job a sync request started."""
    assert response.status_code == 202
    await settle(app)
    job = await client.get(f"/api/connectors/linear/jobs/{response.json()['id']}")
    assert job.status_code == 200
    body: dict[str, Any] = job.json()
    return body


@pytest.fixture
def linear_configured(settings_env: Callable[..., None]) -> None:
    settings_env(linear_api_key="lin_api_test")


@pytest.fixture
def linear_unconfigured(settings_env: Callable[..., None]) -> None:
    settings_env(linear_api_key="")


async def test_status_reports_unconfigured(client: AsyncClient, linear_unconfigured: None) -> None:
    response = await client.get("/api/connectors/linear")

    assert response.status_code == 200
    assert response.json() == {"configured": False, "running": None}


async def test_status_reports_configured(client: AsyncClient, linear_configured: None) -> None:
    response = await client.get("/api/connectors/linear")

    assert response.status_code == 200
    assert response.json() == {"configured": True, "running": None}


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

    first = await _outcome(
        test_app,
        client,
        await client.post("/api/connectors/linear/sync", json={"organization_id": org["id"]}),
    )

    assert first["state"] == "succeeded"
    assert first["summary"] == {
        "teams": 1,
        "projects": 1,
        "work_items": 1,
        "events": 1,
        "divergences": 0,
        "deleted": 0,
        "state_types_filled": 0,
        "rebuilt": 0,
    }
    teams = (await client.get("/api/teams")).json()
    assert teams[0]["external_id"] == "lt1"

    second = await _outcome(
        test_app,
        client,
        await client.post("/api/connectors/linear/sync", json={"organization_id": org["id"]}),
    )

    assert second["summary"] == {
        "teams": 0,
        "projects": 0,
        "work_items": 0,
        "events": 0,
        "divergences": 0,
        "deleted": 0,
        "state_types_filled": 0,
        "rebuilt": 0,
    }


async def test_resync_with_an_assignee_writes_nothing(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    def source() -> FakeDataSource:
        fake = _fake_source()
        fake.work_items = [
            dataclasses.replace(fake.work_items[0], assignee=SourcePerson("u1", "Ada", "a@x.io"))
        ]
        return fake

    test_app.dependency_overrides[get_delivery_data_source] = source
    org = (await client.post("/api/organizations", json={"name": "Acme"})).json()

    url = "/api/connectors/linear/sync"
    await _outcome(test_app, client, await client.post(url, json={"organization_id": org["id"]}))
    second = await _outcome(
        test_app, client, await client.post(url, json={"organization_id": org["id"]})
    )

    assert second["summary"]["work_items"] == 0


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


async def test_a_failing_source_ends_the_job_failed_with_its_error(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = FailingDataSource
    org = (await client.post("/api/organizations", json={"name": "Acme"})).json()

    job = await _outcome(
        test_app,
        client,
        await client.post("/api/connectors/linear/sync", json={"organization_id": org["id"]}),
    )

    assert job["state"] == "failed"
    assert job["error"] == "Linear API returned HTTP 500"
    assert job["summary"] is None
    assert job["finished_at"] is not None


async def test_bootstrap_sync_job_sees_the_new_organization(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    # The request creates the organization and commits it before the job,
    # in its own session, syncs into it.
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source

    job = await _outcome(
        test_app, client, await client.post("/api/connectors/linear/sync", json={})
    )

    assert job["state"] == "succeeded"
    orgs = (await client.get("/api/organizations")).json()
    assert [org["name"] for org in orgs] == ["Acme Workspace"]
    assert job["organization_id"] == orgs[0]["id"]
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


async def test_rebuild_resyncs_events_and_recomputes_history(
    rules_app: FastAPI, rules_client: AsyncClient, linear_configured: None
) -> None:
    rules_app.dependency_overrides[get_delivery_data_source] = _fake_source
    org = (await rules_client.post("/api/organizations", json={"name": "Acme"})).json()
    url = "/api/connectors/linear/sync"
    await _outcome(
        rules_app, rules_client, await rules_client.post(url, json={"organization_id": org["id"]})
    )

    job = await _outcome(
        rules_app,
        rules_client,
        await rules_client.post(url, json={"organization_id": org["id"], "rebuild": True}),
    )
    rules = (await rules_client.get(f"/api/organizations/{org['id']}/metric-rules")).json()

    assert job["rebuild"] is True
    assert (job["summary"]["rebuilt"], job["summary"]["events"]) == (1, 1)
    assert rules["recompute"]["state"] == "idle"
    assert rules["recompute"]["finished_at"] is not None  # history was rewritten


async def test_a_plain_sync_does_not_recompute_history(
    rules_app: FastAPI, rules_client: AsyncClient, linear_configured: None
) -> None:
    rules_app.dependency_overrides[get_delivery_data_source] = _fake_source
    org = (await rules_client.post("/api/organizations", json={"name": "Acme"})).json()

    await _outcome(
        rules_app,
        rules_client,
        await rules_client.post("/api/connectors/linear/sync", json={"organization_id": org["id"]}),
    )
    rules = (await rules_client.get(f"/api/organizations/{org['id']}/metric-rules")).json()

    assert rules["recompute"]["finished_at"] is None


async def test_rebuild_for_an_unknown_organization_is_404_and_leaves_the_runner_usable(
    rules_app: FastAPI, rules_client: AsyncClient, linear_configured: None
) -> None:
    rules_app.dependency_overrides[get_delivery_data_source] = _fake_source

    response = await rules_client.post(
        "/api/connectors/linear/sync", json={"organization_id": str(uuid4()), "rebuild": True}
    )
    async with asyncio.timeout(10):  # a runner-lock regression fails fast, not hangs
        await settle(rules_app)  # must not hang: paused() restarted cleanly
        org = (await rules_client.post("/api/organizations", json={"name": "Acme"})).json()
        recompute = await rules_client.post(
            f"/api/organizations/{org['id']}/metric-rules/recompute"
        )

    assert response.status_code == 404
    assert recompute.status_code == 202


async def test_manual_sync_job_holds_the_sync_job_lock(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    runner = SyncJobRunner(
        test_app.state.sessionmaker, recompute=RecomputeRunner(test_app.state.sessionmaker)
    )
    test_app.state.sync_job_runner = runner
    seen: list[bool] = []

    class LockProbe(FakeDataSource):
        async def fetch_teams(self) -> list[SourceTeam]:
            seen.append(runner.lock.locked())
            return await super().fetch_teams()

    # A lambda, not the class: FastAPI would read FakeDataSource.__init__'s
    # parameters as request parameters.
    test_app.dependency_overrides[get_delivery_data_source] = lambda: LockProbe(
        teams=[SourceTeam(external_id="lt1", name="Platform")]
    )

    job = await _outcome(
        test_app, client, await client.post("/api/connectors/linear/sync", json={})
    )

    assert job["state"] == "succeeded"
    assert seen == [True]
    assert not runner.lock.locked()


async def test_manual_sync_is_recorded_on_the_schedule(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source
    org_id = (await client.post("/api/organizations", json={"name": "Acme"})).json()["id"]
    schedule_url = f"/api/organizations/{org_id}/sync-schedule"
    await client.put(
        schedule_url,
        json={
            "enabled": True,
            "days": [1, 2, 3, 4, 5, 6, 7],
            "window_start": "00:00",
            "window_end": "23:45",
            "interval_minutes": 15,
            "timezone": "UTC",
        },
    )
    assert (await client.get(schedule_url)).json()["last_manual_sync_at"] is None

    await _outcome(
        test_app,
        client,
        await client.post("/api/connectors/linear/sync", json={"organization_id": org_id}),
    )

    assert (await client.get(schedule_url)).json()["last_manual_sync_at"] is not None


def _two_team_source() -> FakeDataSource:
    source = _fake_source()
    source.teams = [*source.teams, SourceTeam(external_id="lt2", name="Mobile")]
    source.work_items = [
        *source.work_items,
        dataclasses.replace(source.work_items[0], external_id="li2", team_external_id="lt2"),
    ]
    return source


async def test_team_sync_pulls_only_that_teams_items(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _two_team_source
    _, team_id = await create_org_and_team(client, external_id="lt1")

    job = await _outcome(
        test_app, client, await client.post(f"/api/connectors/linear/teams/{team_id}/sync")
    )

    assert (job["kind"], job["team_id"]) == ("team", team_id)
    assert job["summary"]["work_items"] == 1
    items = (await client.get("/api/work-items")).json()["items"]
    assert [item["team_id"] for item in items] == [team_id]


async def test_team_sync_captures_the_teams_snapshot(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source
    _, team_id = await create_org_and_team(client, external_id="lt1")

    await _outcome(
        test_app, client, await client.post(f"/api/connectors/linear/teams/{team_id}/sync")
    )

    snapshots = (await client.get(f"/api/metrics/snapshots?team_id={team_id}")).json()
    assert len(snapshots) == 1


async def test_team_sync_leaves_other_teams_snapshots_to_their_own_sync(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    # lt2 is stale after lt1's sync; a snapshot now would freeze today's
    # point from stale data, and the org sync later today would skip it.
    test_app.dependency_overrides[get_delivery_data_source] = _two_team_source
    _, team_id = await create_org_and_team(client, external_id="lt1")

    await _outcome(
        test_app, client, await client.post(f"/api/connectors/linear/teams/{team_id}/sync")
    )

    teams = (await client.get("/api/teams")).json()
    other_id = next(team["id"] for team in teams if team["external_id"] == "lt2")
    assert (await client.get(f"/api/metrics/snapshots?team_id={other_id}")).json() == []


async def test_team_sync_unknown_team_is_404(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source

    response = await client.post(f"/api/connectors/linear/teams/{uuid4()}/sync")

    assert response.status_code == 404


async def test_team_sync_of_a_hand_made_team_is_422(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source
    _, team_id = await create_org_and_team(client)

    response = await client.post(f"/api/connectors/linear/teams/{team_id}/sync")

    assert response.status_code == 422
    assert "nothing to sync" in response.json()["detail"]


async def test_team_sync_returns_409_when_unconfigured(
    client: AsyncClient, linear_unconfigured: None
) -> None:
    response = await client.post(f"/api/connectors/linear/teams/{uuid4()}/sync")

    assert response.status_code == 409


async def test_team_sync_job_holds_the_sync_job_lock(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    runner = SyncJobRunner(
        test_app.state.sessionmaker, recompute=RecomputeRunner(test_app.state.sessionmaker)
    )
    test_app.state.sync_job_runner = runner
    seen: list[bool] = []

    class LockProbe(FakeDataSource):
        async def fetch_teams(self) -> list[SourceTeam]:
            seen.append(runner.lock.locked())
            return await super().fetch_teams()

    test_app.dependency_overrides[get_delivery_data_source] = lambda: LockProbe(
        teams=[SourceTeam(external_id="lt1", name="Platform")]
    )
    _, team_id = await create_org_and_team(client, external_id="lt1")

    job = await _outcome(
        test_app, client, await client.post(f"/api/connectors/linear/teams/{team_id}/sync")
    )

    assert job["state"] == "succeeded"
    assert seen == [True]
    assert not runner.lock.locked()


async def test_team_sync_is_not_recorded_on_the_schedule(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    # One team's sync leaves the others stale: a due slot must still run.
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source
    org_id, team_id = await create_org_and_team(client, external_id="lt1")
    schedule_url = f"/api/organizations/{org_id}/sync-schedule"
    await client.put(
        schedule_url,
        json={
            "enabled": True,
            "days": [1, 2, 3, 4, 5, 6, 7],
            "window_start": "00:00",
            "window_end": "23:45",
            "interval_minutes": 15,
            "timezone": "UTC",
        },
    )

    await _outcome(
        test_app, client, await client.post(f"/api/connectors/linear/teams/{team_id}/sync")
    )

    assert (await client.get(schedule_url)).json()["last_manual_sync_at"] is None


async def test_sync_answers_202_with_a_running_job(
    test_app: FastAPI, client: AsyncClient, linear_configured: None
) -> None:
    test_app.dependency_overrides[get_delivery_data_source] = _fake_source

    response = await client.post("/api/connectors/linear/sync", json={})
    await settle(test_app)

    assert response.status_code == 202
    assert response.json()["state"] == "running"
    assert response.json()["kind"] == "organization"
    assert (response.json()["trigger"], response.json()["finished_at"]) == ("manual", None)


async def test_sync_while_a_covering_job_runs_returns_that_job(
    rules_app: FastAPI, rules_client: AsyncClient, linear_configured: None
) -> None:
    # "Sync now" clicked while a sync of the same organization runs: the
    # user sees that sync's result, not an error and not a second sync.
    source = _BlockingSource()
    rules_app.dependency_overrides[get_delivery_data_source] = lambda: source
    _, team_id = await create_org_and_team(rules_client, external_id="lt1")

    first = await rules_client.post("/api/connectors/linear/sync", json={})
    again = await rules_client.post("/api/connectors/linear/sync", json={})
    team = await rules_client.post(f"/api/connectors/linear/teams/{team_id}/sync")
    source.release.set()
    await settle(rules_app)

    assert (again.status_code, team.status_code) == (202, 202)
    assert first.json()["id"] == again.json()["id"] == team.json()["id"]


async def test_rebuild_while_a_plain_sync_runs_is_409(
    rules_app: FastAPI, rules_client: AsyncClient, linear_configured: None
) -> None:
    source = _BlockingSource()
    rules_app.dependency_overrides[get_delivery_data_source] = lambda: source
    await rules_client.post("/api/organizations", json={"name": "Acme"})

    plain = await rules_client.post("/api/connectors/linear/sync", json={})
    rebuild = await rules_client.post("/api/connectors/linear/sync", json={"rebuild": True})
    source.release.set()
    await settle(rules_app)

    started = datetime.fromisoformat(plain.json()["started_at"])
    assert rebuild.status_code == 409
    assert rebuild.json()["detail"] == (
        f"Another organization sync is running (started {started:%H:%M} UTC); "
        "try again when it finishes"
    )


async def test_unknown_job_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/connectors/linear/jobs/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Sync job not found; Atlas may have restarted before it finished"
    )


async def test_status_reports_the_running_job(
    rules_app: FastAPI, rules_client: AsyncClient, linear_configured: None
) -> None:
    source = _BlockingSource()
    rules_app.dependency_overrides[get_delivery_data_source] = lambda: source
    await rules_client.post("/api/organizations", json={"name": "Acme"})

    job_id = (await rules_client.post("/api/connectors/linear/sync", json={})).json()["id"]
    body = (await rules_client.get("/api/connectors/linear")).json()
    source.release.set()
    await settle(rules_app)

    assert body["running"]["id"] == job_id
    assert (await rules_client.get("/api/connectors/linear")).json()["running"] is None
