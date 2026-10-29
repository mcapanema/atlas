"""Translate GitHub GraphQL payloads into platform-neutral Source* types.

GitHub specifics (field names, deployment status states) stop here —
nothing outside this package sees a GitHub payload.
"""

from datetime import datetime
from typing import Any

from app.domain.codebases.entities import DeploymentStatus
from app.domain.codebases.keys import work_item_keys
from app.domain.sync.source import SourceCodebase, SourceDeployment, SourcePullRequest

_STATE_TO_STATUS = {
    "SUCCESS": DeploymentStatus.SUCCESS,
    "FAILURE": DeploymentStatus.FAILURE,
    "ERROR": DeploymentStatus.FAILURE,
}


def _dt(value: str | None) -> datetime | None:
    # GitHub stamps end in "Z"; fromisoformat reads that as UTC.
    return None if value is None else datetime.fromisoformat(value)


def _required_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def map_codebase(node: dict[str, Any]) -> SourceCodebase:
    return SourceCodebase(external_id=node["id"], name=node["nameWithOwner"], url=node.get("url"))


def map_pull_request(node: dict[str, Any]) -> SourcePullRequest:
    commits = node["commits"]["nodes"]
    first_commit_at = _dt(commits[0]["commit"]["authoredDate"]) if commits else None
    merge_commit = node.get("mergeCommit")
    return SourcePullRequest(
        external_id=node["id"],
        number=node["number"],
        title=node["title"],
        opened_at=_required_dt(node["createdAt"]),
        url=node.get("url"),
        first_commit_at=first_commit_at,
        merged_at=_dt(node.get("mergedAt")),
        closed_at=_dt(node.get("closedAt")),
        merge_commit_sha=merge_commit["oid"] if merge_commit else None,
        work_item_keys=work_item_keys(node["headRefName"], node["title"], node.get("body") or ""),
    )


def map_deployment(node: dict[str, Any]) -> SourceDeployment:
    # The latest non-INACTIVE status decides: INACTIVE only marks a deployment
    # as superseded and says nothing about how it went.
    statuses = sorted(
        (s for s in node["statuses"]["nodes"] if s["state"] != "INACTIVE"),
        key=lambda s: _required_dt(s["createdAt"]),
    )
    status = DeploymentStatus.PENDING
    finished_at: datetime | None = None
    if statuses:
        latest = statuses[-1]
        status = _STATE_TO_STATUS.get(latest["state"], DeploymentStatus.PENDING)
        if status is not DeploymentStatus.PENDING:
            finished_at = _required_dt(latest["createdAt"])
    return SourceDeployment(
        external_id=node["id"],
        environment=node["environment"],
        sha=node["commitOid"],
        started_at=_required_dt(node["createdAt"]),
        status=status,
        finished_at=finished_at,
    )
