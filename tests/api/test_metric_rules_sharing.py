import json
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.api.helpers import create_org_and_team, settle


def _file(workspace: dict[str, Any], teams: list[dict[str, Any]]) -> dict[str, Any]:
    return {"format": "atlas-metric-rules", "version": 1, "workspace": workspace, "teams": teams}


async def test_export_then_import_round_trips(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    org, team = await create_org_and_team(rules_client, external_id="lin-platform")
    await rules_client.patch(
        f"/api/organizations/{org}/metric-rules", json={"aging_percentile": 80}
    )
    await rules_client.patch(f"/api/teams/{team}/metric-rules", json={"wait_state_names": ["QA"]})
    await settle(rules_app)

    export = await rules_client.get(f"/api/organizations/{org}/metric-rules/export")
    exported = export.json()
    response = await rules_client.post(
        f"/api/organizations/{org}/metric-rules/import", json=exported
    )

    assert export.status_code == 200
    assert exported["format"] == "atlas-metric-rules"
    assert exported["version"] == 1
    assert exported["exported_at"]
    assert exported["workspace"] == {"aging_percentile": 80}
    assert exported["teams"] == [
        {
            "name": "Platform",
            "external_id": "lin-platform",
            "overrides": {"wait_state_names": ["QA"]},
        }
    ]
    assert org not in json.dumps(exported)  # no Atlas UUIDs travel
    assert team not in json.dumps(exported)
    assert response.status_code == 200
    assert response.json()["imported_teams"] == ["Platform"]
    assert response.json()["skipped_teams"] == []
    assert response.json()["rules"]["recompute"]["state"] == "idle"


async def test_import_reports_skipped_teams_and_recomputes(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    org, team = await create_org_and_team(rules_client)
    shared = _file(
        {"aging_percentile": 90},
        [
            {
                "name": "platform",
                "external_id": "elsewhere",
                "overrides": {"wait_state_names": ["QA"]},
            },
            {"name": "Ghost", "overrides": {"aging_percentile": 70}},
        ],
    )

    response = await rules_client.post(f"/api/organizations/{org}/metric-rules/import", json=shared)
    await settle(rules_app)
    team_view = (await rules_client.get(f"/api/teams/{team}/metric-rules")).json()

    assert response.status_code == 200
    assert response.json()["imported_teams"] == ["Platform"]
    assert response.json()["skipped_teams"] == ["Ghost"]
    assert response.json()["rules"]["overrides"] == {"aging_percentile": 90}
    assert response.json()["rules"]["recompute"]["state"] == "running"
    assert team_view["overrides"] == {"wait_state_names": ["QA"]}
    assert team_view["effective"]["aging_percentile"] == 90
    assert team_view["recompute"]["state"] == "idle"


async def test_import_reports_a_name_matching_several_teams(rules_client: AsyncClient) -> None:
    org, _ = await create_org_and_team(rules_client)
    for _ in range(2):
        created = await rules_client.post(
            "/api/teams", json={"organization_id": org, "name": "Twin"}
        )
        assert created.status_code == 201
    shared = _file({}, [{"name": "Twin", "overrides": {"aging_percentile": 70}}])

    response = await rules_client.post(f"/api/organizations/{org}/metric-rules/import", json=shared)

    assert response.status_code == 200
    assert response.json()["ambiguous_teams"] == ["Twin"]
    assert response.json()["skipped_teams"] == []
    assert response.json()["imported_teams"] == []


async def test_import_with_one_invalid_team_writes_nothing(rules_client: AsyncClient) -> None:
    org, _ = await create_org_and_team(rules_client)
    shared = _file(
        {"aging_percentile": 90},
        [{"name": "Platform", "overrides": {"aging_percentile": 150}}],
    )

    response = await rules_client.post(f"/api/organizations/{org}/metric-rules/import", json=shared)
    workspace = (await rules_client.get(f"/api/organizations/{org}/metric-rules")).json()

    assert response.status_code == 422
    assert "Platform" in response.json()["detail"]
    assert workspace["overrides"] == {}


@pytest.mark.parametrize(
    "body",
    [
        {"hello": "world"},
        {"format": "atlas-metric-rules", "version": 2, "workspace": {}},
        {"format": "atlas-metric-rules", "version": 1, "workspace": {"bogus": 1}},
        {"format": "atlas-metric-rules", "version": 1, "workspace": {}, "teams": [{"name": ""}]},
        {"format": "atlas-metric-rules", "version": True, "workspace": {}},
        {"format": "atlas-metric-rules", "version": "1", "workspace": {}},
    ],
)
async def test_import_rejects_foreign_or_newer_files(
    rules_client: AsyncClient, body: dict[str, Any]
) -> None:
    org, _ = await create_org_and_team(rules_client)

    response = await rules_client.post(f"/api/organizations/{org}/metric-rules/import", json=body)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "body", [[1, 2], "rules", {"hello": "world"}, {"format": "other", "version": 1}]
)
async def test_import_names_a_non_atlas_file(rules_client: AsyncClient, body: object) -> None:
    org, _ = await create_org_and_team(rules_client)

    response = await rules_client.post(f"/api/organizations/{org}/metric-rules/import", json=body)

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Not an Atlas metric rules file"


async def test_import_names_a_newer_file_version(rules_client: AsyncClient) -> None:
    org, _ = await create_org_and_team(rules_client)
    body = {"format": "atlas-metric-rules", "version": 2, "workspace": {}}

    response = await rules_client.post(f"/api/organizations/{org}/metric-rules/import", json=body)

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == (
        "This rules file is version 2; this Atlas reads version 1. Update Atlas to import it."
    )


async def test_unknown_organization_is_404(rules_client: AsyncClient) -> None:
    missing = uuid4()

    export = await rules_client.get(f"/api/organizations/{missing}/metric-rules/export")
    imported = await rules_client.post(
        f"/api/organizations/{missing}/metric-rules/import", json=_file({}, [])
    )

    assert export.status_code == 404
    assert imported.status_code == 404
