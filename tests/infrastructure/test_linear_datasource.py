import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.domain.events.entities import EventType
from app.infrastructure.connectors.linear import datasource as datasource_module
from app.infrastructure.connectors.linear.client import LinearAPIError, LinearGraphQLClient
from app.infrastructure.connectors.linear.datasource import LinearDataSource
from app.infrastructure.connectors.linear.mapping import HISTORY_PAGE_SIZE


def _page(
    root: str, nodes: list[dict[str, object]], *, end_cursor: str | None = None
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {
                root: {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": end_cursor is not None,
                        "endCursor": end_cursor,
                    },
                }
            }
        },
    )


def _datasource(handler: Callable[[httpx.Request], httpx.Response]) -> LinearDataSource:
    client = LinearGraphQLClient("lin_api_test", transport=httpx.MockTransport(handler))
    return LinearDataSource(client)


async def test_fetch_teams_follows_pagination_cursor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "teams(" in body["query"]
        if body["variables"]["after"] is None:
            return _page("teams", [{"id": "t1", "name": "Platform"}], end_cursor="c1")
        assert body["variables"]["after"] == "c1"
        return _page("teams", [{"id": "t2", "name": "Growth"}])

    teams = await _datasource(handler).fetch_teams()

    assert [t.external_id for t in teams] == ["t1", "t2"]
    assert teams[0].name == "Platform"


async def test_fetch_projects_maps_nodes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _page(
            "projects",
            [{"id": "p1", "name": "Q3 Launch", "teams": {"nodes": [{"id": "t1"}]}}],
        )

    projects = await _datasource(handler).fetch_projects()

    assert projects[0].external_id == "p1"
    assert projects[0].team_external_id == "t1"


async def test_fetch_work_items_maps_issues_and_history() -> None:
    issue_node: dict[str, Any] = {
        "id": "i1",
        "title": "Fix login",
        "createdAt": "2026-07-01T10:00:00.000Z",
        "state": {"name": "In Progress", "type": "started"},
        "team": {"id": "t1"},
        "project": None,
        "history": {
            "nodes": [
                {
                    "id": "h1",
                    "createdAt": "2026-07-02T09:00:00.000Z",
                    "fromState": {"name": "Backlog", "type": "backlog"},
                    "toState": {"name": "In Progress", "type": "started"},
                    "addedLabelIds": [],
                    "removedLabelIds": [],
                }
            ]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        assert "completedAt" in body["query"]
        assert f"history(first: {HISTORY_PAGE_SIZE})" in body["query"]
        return _page("issues", [issue_node])

    items = await _datasource(handler).fetch_work_items()

    assert items[0].external_id == "i1"
    assert [e.type for e in items[0].events] == [EventType.CREATED, EventType.STARTED]
    assert items[0].completed_at is None  # node carries no completedAt


async def test_fetch_work_items_skips_malformed_nodes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    good: dict[str, Any] = {
        "id": "i1",
        "title": "Fix login",
        "createdAt": "2026-07-01T10:00:00.000Z",
        "state": {"name": "In Progress", "type": "started"},
        "team": {"id": "t1"},
        "project": None,
        "history": {"nodes": []},
    }
    bad: dict[str, Any] = {
        "id": "i-bad",
        "title": "No team",
        "createdAt": "2026-07-01T10:00:00.000Z",
        "state": {"name": "Backlog", "type": "backlog"},
        "team": None,  # map_issue does node["team"]["id"] -> TypeError
        "project": None,
        "history": {"nodes": []},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        return _page("issues", [bad, good])

    with caplog.at_level(logging.WARNING):
        items = await _datasource(handler).fetch_work_items()

    assert [i.external_id for i in items] == ["i1"]
    assert any("i-bad" in record.getMessage() for record in caplog.records)


async def test_fetch_work_items_resolves_blocked_labels() -> None:
    issue_node: dict[str, Any] = {
        "id": "i1",
        "title": "Fix login",
        "createdAt": "2026-07-01T10:00:00.000Z",
        "state": {"name": "In Progress", "type": "started"},
        "team": {"id": "t1"},
        "project": None,
        "history": {
            "nodes": [
                {
                    "id": "h1",
                    "createdAt": "2026-07-02T09:00:00.000Z",
                    "fromState": None,
                    "toState": None,
                    "addedLabelIds": ["lbl-1"],
                    "removedLabelIds": [],
                },
                {
                    "id": "h2",
                    "createdAt": "2026-07-03T09:00:00.000Z",
                    "fromState": None,
                    "toState": None,
                    "addedLabelIds": [],
                    "removedLabelIds": ["lbl-1"],
                },
            ]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [{"id": "lbl-1", "name": "Blocked"}])
        assert "addedLabelIds" in body["query"]
        return _page("issues", [issue_node])

    items = await _datasource(handler).fetch_work_items()

    assert [e.type for e in items[0].events] == [
        EventType.CREATED,
        EventType.BLOCKED,
        EventType.UNBLOCKED,
    ]


async def test_pagination_stops_at_page_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(datasource_module, "_MAX_PAGES", 3)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        # hasNextPage forever with a repeating cursor — without a ceiling
        # this loops until the heat death of the workspace.
        return _page("teams", [{"id": "t1", "name": "Loop"}], end_cursor="same")

    with pytest.raises(LinearAPIError, match="pagination exceeded"):
        await _datasource(handler).fetch_teams()

    assert calls == 3


async def test_fetch_organization_name() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "organization" in body["query"]
        return httpx.Response(
            200, json={"data": {"organization": {"name": "Acme Corp"}}}
        )

    assert await _datasource(handler).fetch_organization_name() == "Acme Corp"


async def test_fetch_organization_name_malformed_payload_is_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"organization": None}})

    with pytest.raises(LinearAPIError, match="malformed"):
        await _datasource(handler).fetch_organization_name()
