from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.codebases.entities import Codebase, Deployment, DeploymentStatus, PullRequest

T = datetime(2026, 10, 1, tzinfo=UTC)
NAIVE = datetime(2026, 10, 1)  # noqa: DTZ001 — naive on purpose


def test_codebase_rejects_blank_production_environment() -> None:
    with pytest.raises(ValueError, match="production_environment must not be empty"):
        Codebase(
            organization_id=uuid4(), name="acme/api", external_id="R1", production_environment="  "
        )


def test_codebase_rejects_blank_name() -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        Codebase(organization_id=uuid4(), name=" ", external_id="R1")


def test_codebase_strips_and_defaults_to_unmapped() -> None:
    c = Codebase(organization_id=uuid4(), name=" acme/api ", external_id="R1")
    assert c.name == "acme/api"
    assert c.team_id is None
    assert c.production_environment == "production"


def test_codebase_rejects_naive_last_synced_at() -> None:
    with pytest.raises(ValueError, match="must be timezone-aware"):
        Codebase(
            organization_id=uuid4(),
            name="acme/api",
            external_id="R1",
            last_synced_at=NAIVE,
        )


def test_pull_request_rejects_naive_opened_at() -> None:
    with pytest.raises(ValueError, match="must be timezone-aware"):
        PullRequest(
            codebase_id=uuid4(),
            external_id="P1",
            number=1,
            title="t",
            opened_at=NAIVE,
        )


def test_pull_request_rejects_naive_merged_at() -> None:
    with pytest.raises(ValueError, match="must be timezone-aware"):
        PullRequest(
            codebase_id=uuid4(),
            external_id="P1",
            number=1,
            title="t",
            opened_at=T,
            merged_at=NAIVE,
        )


def test_deployment_defaults_to_pending() -> None:
    d = Deployment(
        codebase_id=uuid4(), external_id="D1", environment="production", sha="abc", started_at=T
    )
    assert d.status is DeploymentStatus.PENDING


def test_deployment_rejects_naive_finished_at() -> None:
    with pytest.raises(ValueError, match="must be timezone-aware"):
        Deployment(
            codebase_id=uuid4(),
            external_id="D1",
            environment="production",
            sha="abc",
            started_at=T,
            finished_at=NAIVE,
        )
