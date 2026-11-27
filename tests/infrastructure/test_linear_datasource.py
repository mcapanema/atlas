import json
import logging
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.domain.events.entities import EventType
from app.domain.sync.source import SourcePerson
from app.infrastructure.connectors import retry as retry_module
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
    assert projects[0].team_external_ids == ("t1",)


async def test_fetch_work_items_maps_issues_and_history() -> None:
    issue_node: dict[str, Any] = {
        "id": "i1",
        "title": "Fix login",
        "url": "https://linear.app/acme/issue/ENG-1/fix-login",
        "assignee": {"id": "u1", "name": "Ada Lovelace"},
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
        assert "\n      url\n" in body["query"]
        assert "\n      assignee { id name email }\n" in body["query"]
        assert "completedAt" in body["query"]
        assert "\n      priority\n" in body["query"]
        assert "canceledAt" in body["query"]
        assert "cycle { id name number startsAt endsAt }" in body["query"]
        assert f"history(first: {HISTORY_PAGE_SIZE})" in body["query"]
        assert "inverseRelations(first: 50)" in body["query"]
        assert "issue { identifier previousIdentifiers }" in body["query"]
        return _page("issues", [issue_node])

    items = await _datasource(handler).fetch_work_items()

    assert items[0].external_id == "i1"
    assert [e.type for e in items[0].events] == [EventType.CREATED, EventType.STARTED]
    assert items[0].completed_at is None  # node carries no completedAt
    assert items[0].url == "https://linear.app/acme/issue/ENG-1/fix-login"
    assert items[0].assignee == SourcePerson("u1", "Ada Lovelace", None)


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


async def test_fetch_work_items_maps_label_history_with_names() -> None:
    issue_node: dict[str, Any] = {
        "id": "i1",
        "title": "Fix login",
        "createdAt": "2026-07-01T10:00:00.000Z",
        # Backlog: a started current state with no transitions would add a
        # synthetic STARTED, which this test isn't about.
        "state": {"name": "Backlog", "type": "backlog"},
        "team": {"id": "t1"},
        "project": None,
        "labelIds": ["lbl-1"],
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
            assert "includeArchived: true" in body["query"]
            return _page("issueLabels", [{"id": "lbl-1", "name": "Blocked"}])
        assert "addedLabelIds" in body["query"]
        assert "labelIds" in body["query"]
        assert "parent { id }" in body["query"]
        assert re.search(r"\bid\s+identifier\s+title\b", body["query"])  # the issue node field
        assert "relationChanges { identifier type }" in body["query"]
        return _page("issues", [issue_node])

    items = await _datasource(handler).fetch_work_items()

    assert [(e.type, e.detail) for e in items[0].events] == [
        (EventType.CREATED, None),
        (EventType.LABEL_ADDED, "Blocked"),
        (EventType.LABEL_REMOVED, "Blocked"),
    ]
    assert items[0].labels == ("Blocked",)


async def test_pagination_recovers_from_a_dropped_connection_mid_way(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr(retry_module, "_sleep", no_sleep)
    second_page_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal second_page_calls
        if json.loads(request.content)["variables"]["after"] is None:
            return _page("teams", [{"id": "t1", "name": "Platform"}], end_cursor="c1")
        second_page_calls += 1
        if second_page_calls == 1:
            raise httpx.ReadError("connection reset by peer")
        return _page("teams", [{"id": "t2", "name": "Growth"}])

    teams = await _datasource(handler).fetch_teams()

    assert [t.external_id for t in teams] == ["t1", "t2"]
    assert second_page_calls == 2


async def test_pagination_stops_at_page_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(datasource_module, "_MAX_PAGES", 3)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        # hasNextPage forever, a new cursor each time — without a ceiling
        # this loops until the heat death of the workspace.
        return _page("teams", [{"id": "t1", "name": "Loop"}], end_cursor=f"c{calls}")

    with pytest.raises(LinearAPIError, match="pagination exceeded"):
        await _datasource(handler).fetch_teams()

    assert calls == 3


async def test_fetch_organization_name() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "organization" in body["query"]
        return httpx.Response(200, json={"data": {"organization": {"name": "Acme Corp"}}})

    assert await _datasource(handler).fetch_organization_name() == "Acme Corp"


async def test_fetch_organization_name_malformed_payload_is_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"organization": None}})

    with pytest.raises(LinearAPIError, match="malformed"):
        await _datasource(handler).fetch_organization_name()


async def test_fetch_work_items_includes_archived_and_skips_trashed() -> None:
    def node(issue_id: str, **extra: object) -> dict[str, Any]:
        return {
            "id": issue_id,
            "title": issue_id,
            "createdAt": "2026-07-01T10:00:00.000Z",
            "state": {"name": "Done", "type": "completed"},
            "team": {"id": "t1"},
            "project": None,
            "history": {"nodes": []},
            **extra,
        }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        # Linear auto-archives closed issues; they are still delivered history.
        assert "includeArchived: true" in body["query"]
        assert "trashed" in body["query"]
        assert "archivedAt" in body["query"]
        return _page(
            "issues",
            [
                node("live", trashed=False),
                node("archived", archivedAt="2026-08-01T00:00:00.000Z", trashed=False),
                node("deleted", archivedAt="2026-08-02T00:00:00.000Z", trashed=True),
            ],
        )

    items = await _datasource(handler).fetch_work_items()

    assert [i.external_id for i in items] == ["live", "archived"]


def test_page_ceiling_covers_a_large_workspace() -> None:
    # 50 issues per page: the ceiling must comfortably exceed today's ~10k
    # issues (incl. archived), or sync aborts before finishing.
    assert datasource_module._MAX_PAGES * 50 >= 50_000


def _issue_node(issue_id: str) -> dict[str, Any]:
    return {
        "id": issue_id,
        "title": issue_id,
        "createdAt": "2026-07-01T10:00:00.000Z",
        "state": {"name": "Todo", "type": "unstarted"},
        "team": {"id": "t1"},
        "project": None,
        "history": {"nodes": []},
    }


async def test_fetch_work_items_for_a_team_filters_every_page() -> None:
    filters: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        assert "filter: $filter" in body["query"]
        filters.append(body["variables"]["filter"])
        if body["variables"]["after"] is None:
            return _page("issues", [_issue_node("i1")], end_cursor="c1")
        return _page("issues", [_issue_node("i2")])

    items = await _datasource(handler).fetch_work_items(team_external_id="t1")

    assert [i.external_id for i in items] == ["i1", "i2"]
    assert filters == [{"team": {"id": {"eq": "t1"}}}] * 2


async def test_fetch_work_items_without_a_team_sends_no_filter() -> None:
    # Omitted, not an explicit null: an org-wide sync sends exactly the
    # variables it always has, so it can't depend on how Linear reads null.
    variables: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        variables.append(body["variables"])
        return _page("issues", [_issue_node("i1")])

    await _datasource(handler).fetch_work_items()

    assert variables == [{"after": None}]


def _transition(entry_id: str, day: int, from_type: str, to_type: str) -> dict[str, Any]:
    return {
        "id": entry_id,
        "createdAt": f"2026-07-0{day}T09:00:00.000Z",
        "fromState": {"name": from_type.title(), "type": from_type},
        "toState": {"name": to_type.title(), "type": to_type},
    }


def _history_page(nodes: list[dict[str, Any]], end_cursor: str | None) -> httpx.Response:
    page_info = {"hasNextPage": end_cursor is not None, "endCursor": end_cursor}
    history = {"nodes": nodes, "pageInfo": page_info}
    return httpx.Response(200, json={"data": {"issue": {"history": history}}})


def _history_entry(entry_id: str, day: int, **change: object) -> dict[str, Any]:
    return {"id": entry_id, "createdAt": f"2026-07-0{day}T09:00:00.000Z", **change}


async def test_fetch_work_items_pages_long_histories() -> None:
    # Linear returns history newest first: page 2 holds the older entries.
    first = _transition("h1", 6, "started", "completed")
    node = {
        **_issue_node("i1"),
        "parent": {"id": "p2"},
        "history": {"nodes": [first], "pageInfo": {"hasNextPage": True, "endCursor": "c1"}},
    }
    older = [
        _history_entry("h2", 5, addedLabelIds=["l1"]),
        _history_entry("h3", 4, fromParentId="p1", toParentId="p2"),
        _history_entry("h4", 3, fromParentId="p0", toParentId="p1"),
    ]
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [{"id": "l1", "name": "Bug"}])
        if "issue(id:" in body["query"]:
            seen.append((body["variables"]["id"], body["variables"]["after"]))
            return _history_page(older, None)
        return _page("issues", [node])

    items = await _datasource(handler).fetch_work_items()

    assert seen == [("i1", "c1")]
    events = {e.external_id: e for e in items[0].events}
    assert events["h1"].type is EventType.COMPLETED
    assert events["h2:label-added:l1"].detail == "Bug"
    assert events["h3:parent"].detail == "p2"
    assert events["h4:parent"].detail == "p1"
    # The creation parent comes from the oldest change, found on page 2.
    assert events["i1:parent-born"].detail == "p0"


async def test_history_pagination_stops_at_page_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(datasource_module, "_MAX_PAGES", 2)
    node = {
        **_issue_node("i1"),
        "history": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "c0"}},
    }
    history_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        if "issue(id:" in body["query"]:
            nonlocal history_calls
            history_calls += 1
            return _history_page([], f"c{history_calls}")
        return _page("issues", [node])

    with pytest.raises(LinearAPIError, match="history pagination exceeded"):
        await _datasource(handler).fetch_work_items()

    assert history_calls == 2


def _vanishing_handler(
    history_answer: httpx.Response,
) -> Callable[[httpx.Request], httpx.Response]:
    """Issues i1 (history goes on after cursor "c1") and i2; history answers as given."""
    partial = {
        **_issue_node("i1"),
        "parent": {"id": "p1"},
        "history": {
            "nodes": [_transition("h1", 2, "unstarted", "started")],
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        if "issue(id:" in body["query"]:
            return history_answer
        return _page("issues", [partial, _issue_node("i2")])

    return handler


async def test_a_vanished_issue_keeps_its_partial_history_and_the_sync_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Deleted between the issues page and its history page: Linear answers
    # the unknown id with GraphQL errors on HTTP 200.
    gone = httpx.Response(
        200, json={"errors": [{"message": "Entity not found: Issue"}], "data": None}
    )

    with caplog.at_level(logging.WARNING):
        items = await _datasource(_vanishing_handler(gone)).fetch_work_items()

    assert [item.external_id for item in items] == ["i1", "i2"]
    assert [e.external_id for e in items[0].events] == ["i1:created", "h1"]
    assert "i1 vanished" in caplog.text
    # The oldest parent change may be on the missing pages: no creation parent.
    assert "i1:parent-born" not in {e.external_id for e in items[0].events}


async def test_a_null_issue_on_a_history_page_keeps_the_partial_history() -> None:
    gone = httpx.Response(200, json={"data": {"issue": None}})

    items = await _datasource(_vanishing_handler(gone)).fetch_work_items()

    assert [item.external_id for item in items] == ["i1", "i2"]


async def test_an_http_error_on_a_history_page_still_fails_the_sync() -> None:
    unauthorized = httpx.Response(401, json={"errors": [{"message": "Authentication required"}]})

    with pytest.raises(LinearAPIError):
        await _datasource(_vanishing_handler(unauthorized)).fetch_work_items()


async def test_issues_paging_fails_fast_on_a_repeated_cursor() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _page("teams", [{"id": "t1", "name": "Loop"}], end_cursor="same")

    with pytest.raises(LinearAPIError, match="returned no new cursor"):
        await _datasource(handler).fetch_teams()

    assert calls == 2


async def test_issues_paging_fails_fast_without_a_cursor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page_info = {"hasNextPage": True, "endCursor": None}
        return httpx.Response(200, json={"data": {"teams": {"nodes": [], "pageInfo": page_info}}})

    with pytest.raises(LinearAPIError, match="returned no new cursor"):
        await _datasource(handler).fetch_teams()


async def test_history_paging_fails_fast_without_a_cursor() -> None:
    node = {
        **_issue_node("i1"),
        "history": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "c1"}},
    }
    history_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal history_calls
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        if "issue(id:" in body["query"]:
            history_calls += 1
            page_info = {"hasNextPage": True, "endCursor": None}
            history = {"nodes": [], "pageInfo": page_info}
            return httpx.Response(200, json={"data": {"issue": {"history": history}}})
        return _page("issues", [node])

    with pytest.raises(LinearAPIError, match="returned no new cursor"):
        await _datasource(handler).fetch_work_items()

    assert history_calls == 1


async def test_a_vanished_issue_answered_with_http_400_keeps_its_partial_history() -> None:
    # Linear may answer an unknown id as a user-input error on HTTP 400.
    gone = httpx.Response(
        400,
        json={
            "errors": [
                {"message": "Entity not found: Issue", "extensions": {"code": "INVALID_INPUT"}}
            ]
        },
    )

    items = await _datasource(_vanishing_handler(gone)).fetch_work_items()

    assert [item.external_id for item in items] == ["i1", "i2"]


async def test_another_graphql_error_on_a_history_page_still_fails_the_sync() -> None:
    # Only "not found" means the issue vanished: any other error on HTTP 200
    # would otherwise cut a live issue's history (and a rebuild would store it).
    failed = httpx.Response(200, json={"errors": [{"message": "Internal error"}], "data": None})

    with pytest.raises(LinearAPIError):
        await _datasource(_vanishing_handler(failed)).fetch_work_items()


async def test_history_paging_fails_fast_when_the_first_page_has_no_cursor() -> None:
    # The first history page comes inside the issues query: without this
    # check the next request would send after=None and fetch it again.
    node = {
        **_issue_node("i1"),
        "history": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": None}},
    }
    history_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal history_calls
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        if "issue(id:" in body["query"]:
            history_calls += 1
            return _history_page([], None)
        return _page("issues", [node])

    with pytest.raises(LinearAPIError, match="returned no new cursor"):
        await _datasource(handler).fetch_work_items()

    assert history_calls == 0


async def test_history_paging_fails_fast_on_a_repeated_cursor() -> None:
    node = {
        **_issue_node("i1"),
        "history": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "c1"}},
    }
    history_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal history_calls
        body = json.loads(request.content)
        if "issueLabels(" in body["query"]:
            return _page("issueLabels", [])
        if "issue(id:" in body["query"]:
            history_calls += 1
            return _history_page([], "c1")  # the cursor it was just sent
        return _page("issues", [node])

    with pytest.raises(LinearAPIError, match="returned no new cursor"):
        await _datasource(handler).fetch_work_items()

    assert history_calls == 1
