import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.infrastructure.connectors.github import datasource as datasource_module
from app.infrastructure.connectors.github.client import GitHubAPIError, GitHubGraphQLClient
from app.infrastructure.connectors.github.datasource import GitHubDataSource


def _connection(nodes: list[dict[str, Any]], *, end_cursor: str | None = None) -> dict[str, Any]:
    return {
        "nodes": nodes,
        "pageInfo": {"hasNextPage": end_cursor is not None, "endCursor": end_cursor},
    }


def _ok(data: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def _datasource(handler: Callable[[httpx.Request], httpx.Response]) -> GitHubDataSource:
    client = GitHubGraphQLClient("ghp_test", transport=httpx.MockTransport(handler))
    return GitHubDataSource(client, "acme")


def _pr(pr_id: str, updated_at: str) -> dict[str, Any]:
    return {
        "id": pr_id,
        "number": 1,
        "title": "t",
        "url": None,
        "body": None,
        "headRefName": "b",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": updated_at,
        "mergedAt": None,
        "closedAt": None,
        "mergeCommit": None,
        "commits": {"nodes": []},
    }


def _deployment(dep_id: str, created_at: str) -> dict[str, Any]:
    return {
        "id": dep_id,
        "environment": "production",
        "commitOid": "abc",
        "createdAt": created_at,
        "statuses": {"nodes": []},
    }


def _day(n: int) -> str:
    return f"2026-07-{n:02d}T00:00:00Z"


async def test_fetch_codebases_paginates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        variables = json.loads(request.content)["variables"]
        assert variables["owner"] == "acme"
        if variables["after"] is None:
            node = {"id": "r1", "nameWithOwner": "acme/a", "url": "u1"}
            return _ok({"repositoryOwner": {"repositories": _connection([node], end_cursor="c1")}})
        assert variables["after"] == "c1"
        node = {"id": "r2", "nameWithOwner": "acme/b", "url": "u2"}
        return _ok({"repositoryOwner": {"repositories": _connection([node])}})

    codebases = await _datasource(handler).fetch_codebases()

    assert [c.external_id for c in codebases] == ["r1", "r2"]
    assert codebases[1].name == "acme/b"


async def test_fetch_codebases_unknown_owner_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok({"repositoryOwner": None})

    with pytest.raises(GitHubAPIError, match="'acme' not found or not visible"):
        await _datasource(handler).fetch_codebases()


async def test_fetch_pull_requests_stops_at_since() -> None:
    requested: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        variables = json.loads(request.content)["variables"]
        assert variables["id"] == "r1"
        requested.append(variables["after"])
        pages = {
            None: ([_pr("p5", _day(5)), _pr("p4", _day(4))], "c1"),
            "c1": ([_pr("p2", _day(2)), _pr("p1", _day(1))], "c2"),
        }
        nodes, cursor = pages[variables["after"]]
        return _ok({"node": {"pullRequests": _connection(nodes, end_cursor=cursor)}})

    since = datetime(2026, 7, 3, tzinfo=UTC)
    prs = await _datasource(handler).fetch_pull_requests("r1", since)

    assert [p.external_id for p in prs] == ["p5", "p4"]
    assert requested == [None, "c1"]


async def test_fetch_pull_requests_keeps_node_stamped_exactly_at_since() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok({"node": {"pullRequests": _connection([_pr("p3", _day(3))])}})

    prs = await _datasource(handler).fetch_pull_requests("r1", datetime(2026, 7, 3, tzinfo=UTC))

    assert [p.external_id for p in prs] == ["p3"]


async def test_fetch_deployments_stops_at_since_and_maps() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        nodes = [_deployment("d5", _day(5)), _deployment("d1", _day(1))]
        return _ok({"node": {"deployments": _connection(nodes)}})

    deployments = await _datasource(handler).fetch_deployments(
        "r1", datetime(2026, 7, 3, tzinfo=UTC)
    )

    assert [d.external_id for d in deployments] == ["d5"]


async def test_fetch_deployments_skips_malformed_node(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        bad = {"id": "d-bad", "createdAt": _day(5)}
        return _ok({"node": {"deployments": _connection([bad, _deployment("d4", _day(4))])}})

    with caplog.at_level(logging.WARNING):
        deployments = await _datasource(handler).fetch_deployments(
            "r1", datetime(2026, 7, 1, tzinfo=UTC)
        )

    assert [d.external_id for d in deployments] == ["d4"]
    assert any("d-bad" in record.getMessage() for record in caplog.records)


async def test_pagination_cap_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(datasource_module, "_MAX_PAGES", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        return _ok({"node": {"pullRequests": _connection([_pr("p", _day(5))], end_cursor="c")}})

    with pytest.raises(GitHubAPIError, match="exceeded 2 pages"):
        await _datasource(handler).fetch_pull_requests("r1", datetime(2026, 7, 1, tzinfo=UTC))


async def test_sends_bearer_token() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return _ok({"repositoryOwner": {"repositories": _connection([])}})

    await _datasource(handler).fetch_codebases()

    assert seen == ["Bearer ghp_test"]
