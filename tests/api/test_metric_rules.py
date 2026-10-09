import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.recompute import RecomputeRunner
from app.api.schemas import MetricRulesOverridesWrite, MetricRulesRead
from app.application.metric_rules.service import MetricRulesService, ScopeRef
from app.application.snapshots.service import SnapshotService
from app.domain.metric_rules.entities import RULE_NAMES
from tests.api.helpers import create_org_and_team, settle


def test_rule_dtos_cover_exactly_the_domain_rules() -> None:
    assert set(MetricRulesRead.model_fields) == set(RULE_NAMES)
    assert set(MetricRulesOverridesWrite.model_fields) == set(RULE_NAMES)


async def test_unknown_scopes_are_404(rules_client: AsyncClient) -> None:
    assert (await rules_client.get(f"/api/organizations/{uuid4()}/metric-rules")).status_code == 404
    assert (await rules_client.get(f"/api/teams/{uuid4()}/metric-rules")).status_code == 404
    patch = await rules_client.patch(f"/api/teams/{uuid4()}/metric-rules", json={})
    assert patch.status_code == 404


async def test_workspace_default_starts_as_built_in(rules_client: AsyncClient) -> None:
    org, _ = await create_org_and_team(rules_client)

    body = (await rules_client.get(f"/api/organizations/{org}/metric-rules")).json()

    assert body["overrides"] == {}
    assert body["effective"] == body["built_in"]
    assert body["effective"]["restart_clock_after_move_back"] is False
    assert body["recompute"]["state"] == "idle"


async def test_team_patch_overrides_then_null_resets(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    _, team = await create_org_and_team(rules_client)

    set_response = await rules_client.patch(
        f"/api/teams/{team}/metric-rules", json={"restart_clock_after_move_back": True}
    )
    await settle(rules_app)
    reset_response = await rules_client.patch(
        f"/api/teams/{team}/metric-rules", json={"restart_clock_after_move_back": None}
    )
    await settle(rules_app)
    final = (await rules_client.get(f"/api/teams/{team}/metric-rules")).json()

    assert set_response.status_code == 200
    assert set_response.json()["overrides"] == {"restart_clock_after_move_back": True}
    assert set_response.json()["effective"]["restart_clock_after_move_back"] is True
    assert set_response.json()["inherited"]["restart_clock_after_move_back"] is False
    assert reset_response.json()["overrides"] == {}
    assert final["recompute"]["state"] == "idle"
    assert final["recompute"]["finished_at"] is not None


async def test_patch_rejects_an_unknown_rule(rules_client: AsyncClient) -> None:
    _, team = await create_org_and_team(rules_client)

    response = await rules_client.patch(f"/api/teams/{team}/metric-rules", json={"bogus": 1})

    assert response.status_code == 422


async def test_patch_rejects_an_invalid_value_naming_the_rule(rules_client: AsyncClient) -> None:
    _, team = await create_org_and_team(rules_client)

    response = await rules_client.patch(f"/api/teams/{team}/metric-rules", json={"healthy_min": 0})

    assert response.status_code == 422
    assert "healthy_min" in response.json()["detail"]


async def test_a_workspace_change_conflicting_with_a_team_is_rejected(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    org, team = await create_org_and_team(rules_client)
    await rules_client.patch(f"/api/teams/{team}/metric-rules", json={"healthy_min": 60})
    await settle(rules_app)

    response = await rules_client.patch(
        f"/api/organizations/{org}/metric-rules", json={"warning_min": 65}
    )

    assert response.status_code == 422
    assert "Platform" in response.json()["detail"]


async def test_recompute_endpoint_runs_and_settles(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    org, _ = await create_org_and_team(rules_client)

    response = await rules_client.post(f"/api/organizations/{org}/metric-rules/recompute")
    await settle(rules_app)
    body = (await rules_client.get(f"/api/organizations/{org}/metric-rules")).json()

    assert response.status_code == 202
    assert body["recompute"]["state"] == "idle"
    assert body["recompute"]["finished_at"] is not None


async def test_a_save_during_a_long_scope_rewrite_is_not_blocked_by_its_write_lock(
    rules_app: FastAPI,
    rules_client: AsyncClient,
    file_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, team = await create_org_and_team(rules_client)
    project = (
        await rules_client.post("/api/projects", json={"team_id": team, "name": "Launch"})
    ).json()["id"]
    in_scope = asyncio.Event()
    release = asyncio.Event()
    scopes: list[ScopeRef] = []

    async def holding_the_write_lock(
        self: SnapshotService, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int:
        scopes.append(ScopeRef(team_id=team_id, project_id=project_id))
        async with file_sessionmaker() as session:  # a real, uncommitted write
            await session.execute(text("UPDATE teams SET name = name"))
            in_scope.set()
            await release.wait()
        return 0

    monkeypatch.setattr(SnapshotService, "recompute_scope", holding_the_write_lock)
    await rules_client.post(f"/api/organizations/{org}/metric-rules/recompute")
    await in_scope.wait()

    response = await asyncio.wait_for(
        rules_client.patch(
            f"/api/teams/{team}/metric-rules", json={"restart_clock_after_move_back": True}
        ),
        timeout=3,
    )
    release.set()
    await settle(rules_app)
    final = (await rules_client.get(f"/api/teams/{team}/metric-rules")).json()

    assert response.status_code == 200
    assert len(scopes) == 3  # the held run was cancelled mid-scope...
    assert set(scopes[1:]) == {  # ...then restarted with both of the organization's scopes
        ScopeRef(team_id=UUID(team)),
        ScopeRef(project_id=UUID(project)),
    }
    assert final["recompute"]["state"] == "idle"


async def test_a_save_while_the_old_run_is_finishing_keeps_the_status_running(
    rules_app: FastAPI,
    rules_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, team = await create_org_and_team(rules_client)
    finishing = asyncio.Event()
    gate = asyncio.Event()
    original_finish = MetricRulesService.finish_recompute
    original_scope = SnapshotService.recompute_scope

    async def finish(self: MetricRulesService, organization_id: UUID, *, error: str | None) -> None:
        await original_finish(self, organization_id, error=error)  # idle, not yet committed
        finishing.set()
        await asyncio.Event().wait()  # parked before the runner's commit

    async def scope(self: SnapshotService, **kwargs: UUID | None) -> int:
        if finishing.is_set():
            await gate.wait()  # hold the restarted run so "running" stays observable
        return await original_scope(self, **kwargs)

    monkeypatch.setattr(MetricRulesService, "finish_recompute", finish)
    monkeypatch.setattr(SnapshotService, "recompute_scope", scope)
    await rules_client.post(f"/api/organizations/{org}/metric-rules/recompute")
    await finishing.wait()

    response = await asyncio.wait_for(
        rules_client.patch(
            f"/api/teams/{team}/metric-rules", json={"restart_clock_after_move_back": True}
        ),
        timeout=3,
    )
    state = (await rules_client.get(f"/api/teams/{team}/metric-rules")).json()["recompute"]["state"]
    monkeypatch.setattr(MetricRulesService, "finish_recompute", original_finish)
    gate.set()
    await settle(rules_app)
    final = (await rules_client.get(f"/api/teams/{team}/metric-rules")).json()

    assert response.status_code == 200
    assert state == "running"
    assert final["recompute"]["state"] == "idle"


async def test_a_save_that_changes_no_rule_commits_before_the_run_restarts(
    rules_app: FastAPI, rules_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, team = await create_org_and_team(rules_client)
    log: list[str] = []
    original_commit = AsyncSession.commit

    async def commit(self: AsyncSession) -> None:
        log.append("commit")
        await original_commit(self)

    def run(self: RecomputeRunner) -> Coroutine[Any, Any, None]:
        log.append("run")  # called at restart; leaves its scopes pending for the next one
        return asyncio.sleep(0)

    monkeypatch.setattr(RecomputeRunner, "_run", run)
    monkeypatch.setattr(AsyncSession, "commit", commit)
    await rules_client.post(f"/api/organizations/{org}/metric-rules/recompute")
    log.clear()

    response = await rules_client.patch(
        f"/api/teams/{team}/metric-rules",
        json={"aging_percentile": 85},  # = inherited
    )
    await settle(rules_app)

    assert response.status_code == 200
    assert log[:2] == ["commit", "run"]


async def test_collection_rules_round_trip_normalized(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    _, team = await create_org_and_team(rules_client)

    response = await rules_client.patch(
        f"/api/teams/{team}/metric-rules",
        json={
            "blocked_label_names": [" On hold "],
            "blocked_state_names": [" Aguardando cliente "],
            "remaining_state_types": ["started", "unstarted"],
            "type_labels": [{"label": "Bug", "type": "bug"}],
        },
    )
    await settle(rules_app)
    rejected = await rules_client.patch(
        f"/api/teams/{team}/metric-rules", json={"remaining_state_types": []}
    )

    effective = response.json()["effective"]
    assert response.status_code == 200
    assert effective["blocked_label_names"] == ["On hold"]
    assert effective["blocked_state_names"] == ["Aguardando cliente"]
    assert effective["remaining_state_types"] == ["unstarted", "started"]
    assert effective["type_labels"] == [{"label": "Bug", "type": "bug"}]
    assert rejected.status_code == 422
    assert "remaining_state_types" in rejected.text
