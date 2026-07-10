# app/infrastructure/connectors/linear/datasource.py
"""DeliveryDataSource adapter backed by Linear's GraphQL API."""

from typing import Any

from app.domain.sync.source import SourceProject, SourceTeam, SourceWorkItem
from app.infrastructure.connectors.linear.client import LinearGraphQLClient
from app.infrastructure.connectors.linear.mapping import map_issue, map_project, map_team

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
        return [map_team(node) for node in await self._nodes(_TEAMS_QUERY, "teams")]

    async def fetch_projects(self) -> list[SourceProject]:
        return [map_project(node) for node in await self._nodes(_PROJECTS_QUERY, "projects")]

    async def fetch_work_items(self) -> list[SourceWorkItem]:
        return [map_issue(node) for node in await self._nodes(_ISSUES_QUERY, "issues")]

    async def _nodes(self, query: str, root: str) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            data = await self._client.execute(query, {"after": cursor})
            connection = data[root]
            nodes.extend(connection["nodes"])
            page_info = connection["pageInfo"]
            if not page_info["hasNextPage"]:
                return nodes
            cursor = page_info["endCursor"]
