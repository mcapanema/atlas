# app/infrastructure/connectors/linear/datasource.py
"""DeliveryDataSource adapter backed by Linear's GraphQL API."""

import logging
from collections.abc import Callable
from typing import Any

from app.domain.sync.source import SourceProject, SourceTeam, SourceWorkItem
from app.infrastructure.connectors.linear.client import LinearAPIError, LinearGraphQLClient
from app.infrastructure.connectors.linear.mapping import map_issue, map_project, map_team

logger = logging.getLogger(__name__)

# ponytail: 200 pages ≈ 10k issues per sync — far past today's target scale.
# Raise it (or paginate per-team) if a workspace ever legitimately exceeds it.
_MAX_PAGES = 200


def _map_tolerantly[T](
    nodes: list[dict[str, Any]], mapper: Callable[[dict[str, Any]], T], kind: str
) -> list[T]:
    """Map nodes one by one; a malformed node is skipped and logged, not fatal."""
    mapped: list[T] = []
    skipped = 0
    for node in nodes:
        try:
            mapped.append(mapper(node))
        except (KeyError, IndexError, TypeError, ValueError):
            skipped += 1
            logger.warning(
                "Skipping malformed Linear %s node %s",
                kind,
                node.get("id", "<no id>"),
                exc_info=True,
            )
    if skipped:
        logger.warning("Skipped %d malformed Linear %s node(s)", skipped, kind)
    return mapped


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

# ponytail: nested history capped at 250 entries per issue — enough for any
# sane issue. Paginate history per-issue if one ever exceeds it.
_ISSUES_QUERY = """
query Issues($after: String) {
  issues(first: 50, after: $after) {
    nodes {
      id
      title
      createdAt
      state { name type }
      team { id }
      project { id }
      history(first: 250) {
        nodes {
          id
          createdAt
          fromState { name type }
          toState { name type }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


class LinearDataSource:
    def __init__(self, client: LinearGraphQLClient) -> None:
        self._client = client

    async def fetch_teams(self) -> list[SourceTeam]:
        return _map_tolerantly(await self._nodes(_TEAMS_QUERY, "teams"), map_team, "team")

    async def fetch_projects(self) -> list[SourceProject]:
        return _map_tolerantly(
            await self._nodes(_PROJECTS_QUERY, "projects"), map_project, "project"
        )

    async def fetch_work_items(self) -> list[SourceWorkItem]:
        return _map_tolerantly(await self._nodes(_ISSUES_QUERY, "issues"), map_issue, "issue")

    async def _nodes(self, query: str, root: str) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(_MAX_PAGES):
            data = await self._client.execute(query, {"after": cursor})
            connection = data[root]
            nodes.extend(connection["nodes"])
            page_info = connection["pageInfo"]
            if not page_info["hasNextPage"]:
                return nodes
            cursor = page_info["endCursor"]
        raise LinearAPIError(
            f"Linear {root} pagination exceeded {_MAX_PAGES} pages; "
            "aborting (possible cursor loop)"
        )
