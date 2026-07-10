import json
from collections.abc import Callable
from typing import Any

import httpx

from app.domain.events.entities import EventType
from app.infrastructure.connectors.linear.client import LinearGraphQLClient
from app.infrastructure.connectors.linear.datasource import LinearDataSource


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
                }
            ]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return _page("issues", [issue_node])

    items = await _datasource(handler).fetch_work_items()

    assert items[0].external_id == "i1"
    assert [e.type for e in items[0].events] == [EventType.CREATED, EventType.STARTED]
