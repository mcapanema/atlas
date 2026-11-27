"""DeliveryDataSource adapter backed by Linear's GraphQL API."""

import logging
from typing import Any

from app.domain.sync.source import SourceProject, SourceTeam, SourceWorkItem
from app.infrastructure.connectors.graphql import map_tolerantly
from app.infrastructure.connectors.linear.client import LinearAPIError, LinearGraphQLClient
from app.infrastructure.connectors.linear.mapping import (
    HISTORY_PAGE_SIZE,
    map_issue,
    map_project,
    map_team,
)

logger = logging.getLogger(__name__)

# Linear's message for an id it does not know (a deleted issue).
_NOT_FOUND = "Entity not found"

# ponytail: 1000 pages ≈ 50k issues (archived included) per sync — 5x the
# largest workspace seen. Raise it (or paginate per-team) if one exceeds it.
_MAX_PAGES = 1000


_ORGANIZATION_QUERY = """
query Organization {
  organization { name }
}
"""

_TEAMS_QUERY = """
query Teams($after: String) {
  teams(first: 100, after: $after) {
    nodes { id name }
    pageInfo { hasNextPage endCursor }
  }
}
"""

_PROJECTS_QUERY = """
query Projects($after: String) {
  projects(first: 100, after: $after) {
    nodes {
      id
      name
      teams(first: 1) { nodes { id } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

_LABELS_QUERY = """
query Labels($after: String) {
  issueLabels(first: 100, after: $after, includeArchived: true) {
    nodes { id name }
    pageInfo { hasNextPage endCursor }
  }
}
"""

# History comes HISTORY_PAGE_SIZE entries at a time: an issue with more is
# paged per issue (_complete_histories) before mapping.
# Archived issues are included: Linear auto-archives closed issues, and
# they are still delivered (or canceled) history; one archived while still
# open reads as canceled (mapping._archive_events). Trashed ones were
# deleted and are skipped in fetch_work_items.
# One list of history fields for both queries, so a page fetched later
# carries what the first page does.
_HISTORY_FIELDS = (
    "id createdAt fromState { name type } toState { name type } "
    "addedLabelIds removedLabelIds relationChanges { identifier type } "
    "fromParentId toParentId"
)
_ISSUES_QUERY = f"""
query Issues($after: String, $filter: IssueFilter) {{
  issues(first: 50, after: $after, filter: $filter, includeArchived: true) {{
    nodes {{
      id
      identifier
      title
      url
      assignee {{ id name email }}
      priority
      cycle {{ id name number startsAt endsAt }}
      createdAt
      completedAt
      canceledAt
      archivedAt
      trashed
      state {{ name type }}
      team {{ id }}
      project {{ id }}
      labelIds
      parent {{ id }}
      inverseRelations(first: 50) {{
        nodes {{ type issue {{ identifier previousIdentifiers }} }}
      }}
      history(first: {HISTORY_PAGE_SIZE}) {{
        nodes {{ {_HISTORY_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""

_ISSUE_HISTORY_QUERY = f"""
query IssueHistory($id: String!, $after: String) {{
  issue(id: $id) {{
    history(first: {HISTORY_PAGE_SIZE}, after: $after) {{
      nodes {{ {_HISTORY_FIELDS} }}
      pageInfo {{ hasNextPage endCursor }}
    }}
  }}
}}
"""


class LinearDataSource:
    def __init__(self, client: LinearGraphQLClient) -> None:
        self._client = client

    async def fetch_organization_name(self) -> str:
        data = await self._client.execute(_ORGANIZATION_QUERY)
        try:
            name = data["organization"]["name"]
        except (KeyError, TypeError) as exc:
            raise LinearAPIError("Linear organization payload is malformed") from exc
        if not isinstance(name, str):
            raise LinearAPIError("Linear organization payload is malformed")
        return name

    async def fetch_teams(self) -> list[SourceTeam]:
        return map_tolerantly(
            await self._nodes(_TEAMS_QUERY, "teams"), map_team, "team", vendor="Linear"
        )

    async def fetch_projects(self) -> list[SourceProject]:
        return map_tolerantly(
            await self._nodes(_PROJECTS_QUERY, "projects"), map_project, "project", vendor="Linear"
        )

    async def fetch_work_items(self, team_external_id: str | None = None) -> list[SourceWorkItem]:
        labels = await self._nodes(_LABELS_QUERY, "issueLabels")
        label_names = {node["id"]: str(node["name"]) for node in labels}
        # No team: the $filter variable is omitted (not null), so the argument
        # is absent and Linear returns every team's issues.
        variables = (
            {}
            if team_external_id is None
            else {"filter": {"team": {"id": {"eq": team_external_id}}}}
        )
        issues = [
            node
            for node in await self._nodes(_ISSUES_QUERY, "issues", variables)
            if not node.get("trashed")
        ]
        await self._complete_histories(issues)
        return map_tolerantly(
            issues, lambda node: map_issue(node, label_names), "issue", vendor="Linear"
        )

    async def _complete_histories(self, issues: list[dict[str, Any]]) -> None:
        """Fetch the rest of every history that has another page, in place."""
        for node in issues:
            history = node.get("history")
            if isinstance(history, dict) and _has_next_page(history):
                await self._complete_history(str(node.get("id")), history)

    async def _complete_history(self, issue_id: str, history: dict[str, Any]) -> None:
        for _ in range(_MAX_PAGES):
            cursor = history["pageInfo"]["endCursor"]
            page = await self._history_page(issue_id, cursor)
            if page is None:
                # Left with hasNextPage true: the mapping reads the history
                # as incomplete and stores no creation parent from it.
                return
            history["nodes"].extend(page["nodes"])
            history["pageInfo"] = page["pageInfo"]
            if not _has_next_page(history):
                return
            _next_cursor(page["pageInfo"], cursor, f"issue {issue_id} history")
        raise LinearAPIError(
            f"Linear issue {issue_id} history pagination exceeded {_MAX_PAGES} pages; aborting"
        )

    async def _history_page(self, issue_id: str, cursor: str | None) -> dict[str, Any] | None:
        """One page of an issue's history; None when the issue vanished mid-sync.

        Linear answers an unknown (deleted) id with an "Entity not found"
        GraphQL error, or with a null issue. Any other failure still fails
        the sync: a swallowed error would cut a live issue's history.
        """
        try:
            data = await self._client.execute(
                _ISSUE_HISTORY_QUERY, {"id": issue_id, "after": cursor}
            )
        except LinearAPIError as exc:
            if _NOT_FOUND not in str(exc):
                raise
            logger.warning("Linear issue %s vanished during history paging: %s", issue_id, exc)
            return None
        if data.get("issue") is None:
            logger.warning(
                "Linear issue %s vanished during history paging: issue is null", issue_id
            )
            return None
        page: dict[str, Any] = data["issue"]["history"]
        return page

    async def _nodes(
        self, query: str, root: str, variables: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(_MAX_PAGES):
            data = await self._client.execute(query, {**(variables or {}), "after": cursor})
            connection = data[root]
            nodes.extend(connection["nodes"])
            page_info = connection["pageInfo"]
            if not page_info["hasNextPage"]:
                return nodes
            cursor = _next_cursor(page_info, cursor, root)
        raise LinearAPIError(
            f"Linear {root} pagination exceeded {_MAX_PAGES} pages; aborting (possible cursor loop)"
        )


def _has_next_page(history: dict[str, Any]) -> bool:
    page_info = history.get("pageInfo")
    return isinstance(page_info, dict) and bool(page_info.get("hasNextPage"))


def _next_cursor(page_info: dict[str, Any], sent: str | None, what: str) -> str:
    """The cursor for the page after this one; raise when there is none.

    A page that says it has a next page but gives no new cursor would make
    the loop fetch the same page again until the page ceiling.
    """
    cursor = page_info.get("endCursor")
    if not cursor or cursor == sent:
        raise LinearAPIError(f"Linear {what} pagination returned no new cursor; aborting")
    return str(cursor)
