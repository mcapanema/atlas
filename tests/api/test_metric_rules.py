from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient

from app.api.schemas import MetricRulesOverridesWrite, MetricRulesRead
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
