from datetime import UTC, datetime
from typing import Any

from app.domain.codebases.entities import DeploymentStatus
from app.infrastructure.connectors.github.mapping import (
    map_codebase,
    map_deployment,
    map_pull_request,
)

T1 = "2026-07-01T10:00:00Z"
T2 = "2026-07-01T11:00:00Z"


def deployment_node(statuses: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "id": "d1",
        "environment": "production",
        "commitOid": "abc123",
        "createdAt": "2026-07-01T09:00:00Z",
        "statuses": {"nodes": [{"state": s, "createdAt": at} for s, at in statuses]},
    }


def pull_request_node(**overrides: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": "pr1",
        "number": 7,
        "title": "Fix login",
        "url": "https://github.com/acme/api/pull/7",
        "body": "details",
        "headRefName": "feature/x",
        "createdAt": "2026-07-01T10:00:00Z",
        "updatedAt": "2026-07-02T10:00:00Z",
        "mergedAt": None,
        "closedAt": None,
        "mergeCommit": None,
        "commits": {"nodes": [{"commit": {"authoredDate": "2026-06-30T08:00:00Z"}}]},
    }
    return node | overrides


def test_map_codebase() -> None:
    codebase = map_codebase(
        {"id": "r1", "nameWithOwner": "acme/api", "url": "https://github.com/acme/api"}
    )
    assert (codebase.external_id, codebase.name, codebase.url) == (
        "r1",
        "acme/api",
        "https://github.com/acme/api",
    )


def test_inactive_after_success_reads_success() -> None:
    node = deployment_node(statuses=[("SUCCESS", T1), ("INACTIVE", T2)])
    deployment = map_deployment(node)
    assert (deployment.status, deployment.finished_at) == (
        DeploymentStatus.SUCCESS,
        datetime(2026, 7, 1, 10, tzinfo=UTC),
    )
    assert deployment.sha == "abc123"
    assert deployment.environment == "production"


def test_error_reads_failure() -> None:
    deployment = map_deployment(deployment_node(statuses=[("ERROR", T1)]))
    assert deployment.status is DeploymentStatus.FAILURE
    assert deployment.finished_at == datetime(2026, 7, 1, 10, tzinfo=UTC)


def test_rerun_success_after_failure_reads_success() -> None:
    deployment = map_deployment(deployment_node(statuses=[("SUCCESS", T2), ("FAILURE", T1)]))
    assert (deployment.status, deployment.finished_at) == (
        DeploymentStatus.SUCCESS,
        datetime(2026, 7, 1, 11, tzinfo=UTC),
    )


def test_in_progress_or_no_status_reads_pending() -> None:
    for statuses in ([("IN_PROGRESS", T1)], [("INACTIVE", T1)], []):
        deployment = map_deployment(deployment_node(statuses=statuses))
        assert (deployment.status, deployment.finished_at) == (DeploymentStatus.PENDING, None)


def test_pull_request_keys_come_from_branch_title_and_body() -> None:
    pr = map_pull_request(
        pull_request_node(headRefName="murilo/dep-1-x", title="ENG-2 fix", body=None)
    )
    assert pr.work_item_keys == ("DEP-1", "ENG-2")
    assert pr.first_commit_at == datetime(2026, 6, 30, 8, tzinfo=UTC)
    assert pr.number == 7


def test_open_pull_request_has_no_merge_fields() -> None:
    pr = map_pull_request(pull_request_node())
    assert (pr.merged_at, pr.closed_at, pr.merge_commit_sha) == (None, None, None)


def test_merged_pull_request_carries_merge_fields() -> None:
    pr = map_pull_request(
        pull_request_node(
            mergedAt="2026-07-03T10:00:00Z",
            closedAt="2026-07-03T10:00:00Z",
            mergeCommit={"oid": "def456"},
        )
    )
    assert pr.merge_commit_sha == "def456"
    assert pr.merged_at == datetime(2026, 7, 3, 10, tzinfo=UTC)


def test_pull_request_without_commits_has_no_first_commit() -> None:
    assert map_pull_request(pull_request_node(commits={"nodes": []})).first_commit_at is None
