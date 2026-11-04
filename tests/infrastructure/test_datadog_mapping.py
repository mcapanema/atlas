from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.codebases.entities import DeploymentStatus
from app.domain.sync.source import SourceCodebase
from app.infrastructure.connectors.datadog.mapping import (
    map_deployment,
    map_incident,
    map_service,
)


def test_map_service_uses_a_prefixed_external_id() -> None:
    assert map_service({"attributes": {"name": "api"}}) == SourceCodebase(
        "datadog:service:api", "api"
    )


def test_map_deployment_is_success_when_finished() -> None:
    node = {
        "id": "d1",
        "attributes": {
            "env": "prod",
            "git": {"commit_sha": "abc"},
            "started_at": "2024-05-01T10:00:00Z",
            "finished_at": "2024-05-01T10:05:00+00:00",
        },
    }
    deployment = map_deployment(node)
    assert deployment.external_id == "datadog:deployment:d1"
    assert deployment.environment == "prod"
    assert deployment.sha == "abc"
    assert deployment.status is DeploymentStatus.SUCCESS
    assert deployment.started_at == datetime(2024, 5, 1, 10, 0, tzinfo=UTC)
    assert deployment.finished_at == datetime(2024, 5, 1, 10, 5, tzinfo=UTC)


def test_map_deployment_is_pending_when_unfinished_with_defaults() -> None:
    node = {"id": "d2", "attributes": {"started_at": "2024-05-01T10:00:00.5+02:00"}}
    deployment = map_deployment(node)
    assert deployment.status is DeploymentStatus.PENDING
    assert deployment.finished_at is None
    assert deployment.environment == ""
    assert deployment.sha == ""
    assert deployment.started_at == datetime(2024, 5, 1, 8, 0, 0, 500000, tzinfo=UTC)


def _incident(**attributes: Any) -> dict[str, Any]:
    return {
        "id": "uuid-1",
        "attributes": {
            "title": "DB down",
            "public_id": 42,
            "created": "2024-05-01T10:00:00+00:00",
            **attributes,
        },
    }


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (None, ()),
        ({}, ()),
        ({"services": None}, ()),
        ({"services": {"value": None}}, ()),
        ({"services": {"value": "api"}}, ("api",)),
        ({"services": {"value": ["api", "web"]}}, ("api", "web")),
    ],
)
def test_map_incident_services_shapes(fields: Any, expected: tuple[str, ...]) -> None:
    assert map_incident(_incident(fields=fields), "datadoghq.com").services == expected


def test_map_incident_basics() -> None:
    incident = map_incident(
        _incident(
            resolved="2024-05-01T11:00:00+00:00",
            fields={"severity": {"value": "SEV-1"}},
        ),
        "datadoghq.eu",
    )
    assert incident.external_id == "datadog:incident:uuid-1"
    assert incident.title == "DB down"
    assert incident.opened_at == datetime(2024, 5, 1, 10, tzinfo=UTC)
    assert incident.restored_at == datetime(2024, 5, 1, 11, tzinfo=UTC)
    assert incident.severity == "SEV-1"
    assert incident.url == "https://app.datadoghq.eu/incidents/42"


def test_map_incident_open_has_no_restored_at_or_severity() -> None:
    incident = map_incident(_incident(), "datadoghq.com")
    assert incident.restored_at is None
    assert incident.severity is None


def test_map_incident_prefers_customer_impact_times() -> None:
    incident = map_incident(
        _incident(
            customer_impact_start="2024-05-01T10:30:00Z",
            customer_impact_end="2024-05-01T10:45:00Z",
            resolved="2024-05-01T11:00:00Z",
        ),
        "datadoghq.com",
    )
    assert incident.opened_at == datetime(2024, 5, 1, 10, 30, tzinfo=UTC)
    assert incident.restored_at == datetime(2024, 5, 1, 10, 45, tzinfo=UTC)
