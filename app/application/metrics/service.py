from collections import Counter
from collections.abc import Set as AbstractSet
from datetime import UTC, datetime
from uuid import UUID

from app.application.metric_rules.resolver import MetricRulesResolver
from app.application.scope import ScopeData, ScopeSampleLoader, ScopeSamples
from app.domain.events.repository import EventRepository
from app.domain.metrics.aging import AgingWip, compute_aging_wip
from app.domain.metrics.distribution import (
    LeadTimeDistribution,
    compute_lead_time_distribution,
)
from app.domain.metrics.health import DeliveryHealth, compute_delivery_health
from app.domain.metrics.history import FlowHistory, compute_flow_history
from app.domain.metrics.state_time import StateTimes, compute_state_times
from app.domain.metrics.summary import FlowMetrics, compute_flow_metrics
from app.domain.metrics.windows import CHART_WINDOW_DAYS, STATS_WINDOW_DAYS
from app.domain.projects.repository import ProjectRepository
from app.domain.teams.repository import TeamRepository
from app.domain.work_items.entities import WorkItemType
from app.domain.work_items.repository import WorkItemRepository


class MetricsService:
    """Application use cases for flow metrics."""

    def __init__(
        self,
        work_items: WorkItemRepository,
        events: EventRepository,
        rules: MetricRulesResolver | None = None,
        *,
        teams: TeamRepository | None = None,
        projects: ProjectRepository | None = None,
    ) -> None:
        self._scope = ScopeSampleLoader(work_items, events, rules)
        self._teams = teams
        self._projects = projects

    async def load_scope_data(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        types: AbstractSet[WorkItemType] | None = None,
        exclude_states: AbstractSet[str] | None = None,
    ) -> ScopeData:
        """The scope's raw picture, for as-of replays (snapshots, recompute, explicit periods)."""
        return await self._scope.load_data(
            team_id=team_id, project_id=project_id, types=types, exclude_states=exclude_states
        )

    async def load_scope(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        types: AbstractSet[WorkItemType] | None = None,
        exclude_states: AbstractSet[str] | None = None,
    ) -> ScopeSamples:
        """One scope load, shareable across the analytics calls via `scope=`."""
        return await self._scope.load(
            team_id=team_id,
            project_id=project_id,
            types=types,
            exclude_states=exclude_states,
        )

    async def get_flow_metrics(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = STATS_WINDOW_DAYS,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> FlowMetrics:
        """Compute the scope's flow metrics over the trailing window ending at `now`."""
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_flow_metrics(scope.samples, now=window_end, window_days=window_days)

    async def get_state_times(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = STATS_WINDOW_DAYS,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> StateTimes:
        """Time in each workflow state and the bottleneck over the trailing window."""
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_state_times(
            scope.streams,
            scope.samples,
            now=window_end,
            window_days=window_days,
            rules=scope.rules,
            stream_rules=scope.stream_rules,
            stream_teams=await self._stream_teams(scope),
        )

    async def _stream_teams(self, scope: ScopeSamples) -> list[str | None] | None:
        """Each stream's team name when the scope spans teams; None for one team.

        A team the repository no longer knows is labelled by its id. Teams
        that share a name get the first 8 characters of their id after it, so
        their rows stay apart.
        """
        team_ids = [item.team_id for item, _ in scope.items_with_samples]
        if self._teams is None or len(set(team_ids)) < 2:
            return None
        names: dict[UUID, str] = {}
        for team_id in set(team_ids):
            team = await self._teams.get(team_id)
            names[team_id] = team.name if team is not None else str(team_id)
        clashes = {name for name, count in Counter(names.values()).items() if count > 1}
        for team_id, name in names.items():
            if name in clashes:
                names[team_id] = f"{name} ({str(team_id)[:8]})"
        return [names[team_id] for team_id in team_ids]

    async def get_flow_history(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = CHART_WINDOW_DAYS,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> FlowHistory:
        """Compute the scope's chart time series over the trailing window."""
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_flow_history(
            scope.streams,
            samples=scope.samples,
            stream_rules=scope.stream_rules,
            rules=scope.rules,
            now=window_end,
            window_days=window_days,
            synced_at=await self._synced_at(team_id, project_id),
        )

    async def _synced_at(self, team_id: UUID | None, project_id: UUID | None) -> datetime | None:
        """The scope's team's last sync (a project's home team); None if unknown."""
        if project_id is not None and self._projects is not None:
            project = await self._projects.get(project_id)
            team_id = project.team_id if project is not None else None
        if team_id is None or self._teams is None:
            return None
        team = await self._teams.get(team_id)
        return team.last_synced_at if team is not None else None

    async def get_lead_time_distribution(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = CHART_WINDOW_DAYS,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> LeadTimeDistribution:
        """Histogram of lead times for scope items completed in the trailing window."""
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_lead_time_distribution(
            scope.samples, now=window_end, window_days=window_days
        )

    async def get_aging_wip(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> AgingWip:
        """Ages of the scope's current in-progress items, oldest first."""
        at = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_aging_wip(
            scope.items_with_samples,
            now=at,
            aging_percentile=scope.rules.aging_percentile,
            history_days=scope.rules.aging_history_days,
        )

    async def get_delivery_health(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = STATS_WINDOW_DAYS,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> DeliveryHealth:
        """Composite delivery-health score over the trailing window ending at `now`."""
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)
        return compute_delivery_health(
            scope.streams,
            samples=scope.samples,
            rules=scope.rules,
            now=window_end,
            window_days=window_days,
        )
