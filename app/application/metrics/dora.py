from datetime import UTC, datetime
from uuid import UUID

from app.application.scope import ScopeSamples
from app.domain.codebases.repository import (
    CodebaseRepository,
    DeploymentRepository,
    PullRequestRepository,
)
from app.domain.metrics.dora import DoraMetrics, Incident, compute_dora
from app.domain.metrics.windows import STATS_WINDOW_DAYS
from app.domain.teams.repository import TeamRepository


class DoraService:
    """DORA metrics for one team: its codebases' deployments and pull requests
    plus the scope's incident-labelled work items."""

    def __init__(
        self,
        codebases: CodebaseRepository,
        deployments: DeploymentRepository,
        pull_requests: PullRequestRepository,
        teams: TeamRepository,
    ) -> None:
        self._codebases = codebases
        self._deployments = deployments
        self._pull_requests = pull_requests
        self._teams = teams

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
        incidents = [
            Incident(sample.created_at, sample.completed_at)
            for item, sample in scope.items_with_samples
            if not sample.canceled and any(scope.rules.is_incident_label(x) for x in item.labels)
        ]
        return compute_dora(
            mapped,
            deployments,
            pull_requests,
            incidents,
            now=now or datetime.now(UTC),
            window_days=window_days,
            min_sample=scope.rules.health_min_sample,
        )
