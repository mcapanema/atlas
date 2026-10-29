"""CodeHostSource adapter backed by GitHub's GraphQL API."""

from datetime import datetime
from typing import Any

from app.domain.sync.source import SourceCodebase, SourceDeployment, SourcePullRequest
from app.infrastructure.connectors.github.client import GitHubAPIError, GitHubGraphQLClient
from app.infrastructure.connectors.github.mapping import (
    map_codebase,
    map_deployment,
    map_pull_request,
)
from app.infrastructure.connectors.graphql import map_tolerantly

# ponytail: 1000 pages bounds one sync at 100k repositories or 50k pull
# requests/deployments per codebase; it mainly guards against a cursor loop.
_MAX_PAGES = 1000

_CODEBASES_QUERY = """
query Codebases($owner: String!, $after: String) {
  repositoryOwner(login: $owner) {
    repositories(first: 100, after: $after, orderBy: {field: NAME, direction: ASC}) {
      nodes { id nameWithOwner url }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

_PULL_REQUESTS_QUERY = """
query PullRequests($id: ID!, $after: String) {
  node(id: $id) { ... on Repository {
    pullRequests(first: 50, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        id number title url body headRefName createdAt updatedAt mergedAt closedAt
        mergeCommit { oid }
        commits(first: 1) { nodes { commit { authoredDate } } }
      }
      pageInfo { hasNextPage endCursor }
    }
  } }
}
"""

_DEPLOYMENTS_QUERY = """
query Deployments($id: ID!, $after: String) {
  node(id: $id) { ... on Repository {
    deployments(first: 50, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { id environment commitOid createdAt statuses(first: 20) { nodes { state createdAt } } }
      pageInfo { hasNextPage endCursor }
    }
  } }
}
"""


class GitHubDataSource:
    def __init__(self, client: GitHubGraphQLClient, owner: str) -> None:
        self._client = client
        self._owner = owner

    async def fetch_codebases(self) -> list[SourceCodebase]:
        owner = self._owner
        nodes: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(_MAX_PAGES):
            data = await self._client.execute(_CODEBASES_QUERY, {"owner": owner, "after": cursor})
            if data["repositoryOwner"] is None:
                raise GitHubAPIError(
                    f"GitHub owner {owner!r} not found or not visible to the token"
                )
            connection = data["repositoryOwner"]["repositories"]
            nodes.extend(connection["nodes"])
            if not connection["pageInfo"]["hasNextPage"]:
                return map_tolerantly(nodes, map_codebase, "repository", vendor="GitHub")
            cursor = connection["pageInfo"]["endCursor"]
        raise self._too_many_pages("repositories")

    async def fetch_pull_requests(
        self, codebase_external_id: str, since: datetime
    ) -> list[SourcePullRequest]:
        nodes = await self._since_nodes(
            _PULL_REQUESTS_QUERY, codebase_external_id, "pullRequests", "updatedAt", since
        )
        return map_tolerantly(nodes, map_pull_request, "pull request", vendor="GitHub")

    async def fetch_deployments(
        self, codebase_external_id: str, since: datetime
    ) -> list[SourceDeployment]:
        nodes = await self._since_nodes(
            _DEPLOYMENTS_QUERY, codebase_external_id, "deployments", "createdAt", since
        )
        return map_tolerantly(nodes, map_deployment, "deployment", vendor="GitHub")

    async def _since_nodes(
        self, query: str, repo_id: str, root: str, stamp_field: str, since: datetime
    ) -> list[dict[str, Any]]:
        """Newest-first pages up to the first page that reaches back before `since`.

        Keeps nodes stamped at or after `since`. A node whose stamp is missing
        or unreadable is kept (and stops nothing) so the tolerant mapper can
        log it instead of a bad stamp aborting the sync.
        """
        kept: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(_MAX_PAGES):
            data = await self._client.execute(query, {"id": repo_id, "after": cursor})
            connection = data["node"][root]
            page = connection["nodes"]
            kept.extend(n for n in page if _stamp_ok(n, stamp_field, since, keep=True))
            page_info = connection["pageInfo"]
            exhausted = not page_info["hasNextPage"]
            if exhausted or (page and not _stamp_ok(page[-1], stamp_field, since, keep=False)):
                return kept
            cursor = page_info["endCursor"]
        raise self._too_many_pages(root)

    @staticmethod
    def _too_many_pages(root: str) -> GitHubAPIError:
        return GitHubAPIError(
            f"GitHub {root} pagination exceeded {_MAX_PAGES} pages; aborting (possible cursor loop)"
        )


def _stamp_ok(node: dict[str, Any], field: str, since: datetime, *, keep: bool) -> bool:
    """True if the node's stamp is at/after `since`; `keep` decides the unreadable case."""
    try:
        return datetime.fromisoformat(node[field]) >= since
    except (KeyError, TypeError, ValueError):
        return keep
