from datetime import UTC, datetime
from uuid import UUID

from app.application.scope import ScopeSamples
from app.domain.codebases.entities import Codebase, CodebaseSource
from app.domain.codebases.repository import (
    CodebaseRepository,
    DeploymentRepository,
    PullRequestRepository,
)
from app.domain.incidents.repository import ServiceIncidentRepository
from app.domain.metric_rules.entities import MetricRules
from app.domain.metrics.dora import DoraMetrics, Incident, compute_dora, drop_duplicate_releases
from app.domain.metrics.windows import STATS_WINDOW_DAYS
from app.domain.teams.repository import TeamRepository


class DoraService:
    """DORA metrics for one team: its codebases' deployments and pull requests
    plus one incident source: the scope's incident-labelled work items or the
    stored Datadog incidents (the `incident_source` rule)."""

    def __init__(
        self,
        codebases: CodebaseRepository,
        deployments: DeploymentRepository,
        pull_requests: PullRequestRepository,
        teams: TeamRepository,
        incidents: ServiceIncidentRepository,
    ) -> None:
        self._codebases = codebases
        self._deployments = deployments
        self._pull_requests = pull_requests
        self._teams = teams
        self._incidents = incidents

    async def get_dora(
        self,
        *,
        team_id: UUID,
        scope: ScopeSamples,
        window_days: int = STATS_WINDOW_DAYS,
        now: datetime | None = None,
    ) -> DoraMetrics:
        team = await self._teams.get(team_id)
        if team is None:
            raise ValueError(f"Team {team_id} not found")
        mapped = [
            c for c in await self._codebases.list(team.organization_id) if c.team_id == team_id
        ]
        ids = [c.id for c in mapped]
        # ponytail: loads every stored deployment and pull request of the team's
        # codebases (bounded by the 180-day backfill plus growth); upgrade path:
        # a `since` argument on the two `list_for_codebases` ports.
        deployments = await self._deployments.list_for_codebases(ids)
        pull_requests = await self._pull_requests.list_for_codebases(ids)
        incidents = await self._incidents_of(team.organization_id, mapped, scope)
        kept, duplicates = drop_duplicate_releases(mapped, deployments)
        return compute_dora(
            mapped,
            kept,
            pull_requests,
            incidents,
            now=now or datetime.now(UTC),
            window_days=window_days,
            min_sample=scope.rules.health_min_sample,
            duplicate_deployments=duplicates,
        )

    async def _incidents_of(
        self, organization_id: UUID, mapped: list[Codebase], scope: ScopeSamples
    ) -> list[Incident]:
        """The team's incidents from the one source its rules choose."""
        source = scope.rules.incident_source
        if source != "linear":
            datadog = await self._datadog_incidents(organization_id, mapped)
            if datadog or source == "datadog":
                return datadog
        return _linear_incidents(scope)

    async def _datadog_incidents(
        self, organization_id: UUID, mapped: list[Codebase]
    ) -> list[Incident]:
        """Stored Datadog incidents on a service the team maps, at any time."""
        names = {c.name.strip().casefold() for c in mapped if c.source is CodebaseSource.DATADOG}
        if not names:
            return []
        return [
            Incident(i.opened_at, i.restored_at)
            for i in await self._incidents.list(organization_id)
            if names & {service.strip().casefold() for service in i.services}
        ]


def _linear_incidents(scope: ScopeSamples) -> list[Incident]:
    rules: MetricRules = scope.rules
    return [
        Incident(sample.created_at, sample.completed_at)
        for item, sample in scope.items_with_samples
        if not sample.canceled and any(rules.is_incident_label(x) for x in item.labels)
    ]
