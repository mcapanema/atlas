"""Pure Datadog payload to `Source*` mapping. Raises on malformed nodes."""

from datetime import UTC, datetime
from typing import Any

from app.domain.codebases.entities import DeploymentStatus
from app.domain.sync.source import SourceCodebase, SourceDeployment, SourceIncident


def parse_time(value: str) -> datetime:
    """Parse an ISO-8601 stamp with an offset (or `Z`) into an aware UTC datetime."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Datadog timestamp {value!r} has no offset")
    return parsed.astimezone(UTC)


def _optional_time(value: str | None) -> datetime | None:
    return parse_time(value) if value else None


def map_service(node: dict[str, Any]) -> SourceCodebase:
    name = node["attributes"]["name"]
    return SourceCodebase(f"datadog:service:{name}", name)


def map_deployment(node: dict[str, Any]) -> SourceDeployment:
    attributes = node["attributes"]
    finished_at = _optional_time(attributes.get("finished_at"))
    return SourceDeployment(
        external_id=f"datadog:deployment:{node['id']}",
        environment=attributes.get("env") or "",
        sha=(attributes.get("git") or {}).get("commit_sha") or "",
        started_at=parse_time(attributes["started_at"]),
        status=DeploymentStatus.SUCCESS if finished_at else DeploymentStatus.PENDING,
        finished_at=finished_at,
    )


def _field_value(fields: dict[str, Any] | None, name: str) -> Any:
    return ((fields or {}).get(name) or {}).get("value")


def _services(fields: dict[str, Any] | None) -> tuple[str, ...]:
    value = _field_value(fields, "services")
    if value is None:
        return ()
    return (value,) if isinstance(value, str) else tuple(value)


def _severity(attributes: dict[str, Any]) -> str | None:
    """Top-level `severity` first, then the `fields` form; UNKNOWN and blank mean none."""
    for value in (attributes.get("severity"), _field_value(attributes.get("fields"), "severity")):
        if value and value != "UNKNOWN":
            return str(value)
    return None


def map_incident(node: dict[str, Any], site: str) -> SourceIncident:
    attributes = node["attributes"]
    fields = attributes.get("fields")
    opened_at = attributes.get("customer_impact_start") or attributes["created"]
    restored_at = attributes.get("customer_impact_end") or attributes.get("resolved")
    return SourceIncident(
        external_id=f"datadog:incident:{node['id']}",
        title=attributes["title"],
        opened_at=parse_time(opened_at),
        restored_at=_optional_time(restored_at),
        services=_services(fields),
        severity=_severity(attributes),
        url=f"https://app.{site}/incidents/{attributes['public_id']}",
    )
