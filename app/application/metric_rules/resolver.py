"""Resolve the MetricRules a scope load folds with: built-in ⊕ workspace ⊕ team."""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from uuid import UUID

from app.domain.metric_rules.entities import (
    DEFAULT_RULES,
    MetricRules,
    RuleOverrides,
    resolve_rules,
    unknown_rule_names,
)
from app.domain.metric_rules.repository import MetricRuleOverridesRepository
from app.domain.projects.repository import ProjectRepository
from app.domain.teams.repository import TeamRepository

logger = logging.getLogger(__name__)


def resolve_layers(
    *layers: Mapping[str, object],
    subject: str,
    warned: list[Mapping[str, object]] | None = None,
) -> MetricRules:
    """Resolve override layers over the built-ins; unknown keys warn, invalid ones fall back.

    `warned` lets one load share the layers it already reported, so a layer
    several resolutions fold in (the workspace's) is reported once. It holds
    the layers themselves, compared by identity, so none is freed and its
    identity reused while the load runs.
    """
    seen = warned if warned is not None else []
    for layer in layers:
        if any(layer is done for done in seen):
            continue
        seen.append(layer)
        if unknown := unknown_rule_names(layer):
            logger.warning("Ignoring unknown metric rule(s) %s for %s", ", ".join(unknown), subject)
    try:
        return resolve_rules(*layers)
    except ValueError:
        logger.exception("Invalid stored metric rules for %s; using built-in", subject)
        return DEFAULT_RULES


@dataclass(frozen=True)
class ResolvedRules:
    """The scope's rules (health, calendar, windows) and each involved team's (lifecycle)."""

    scope: MetricRules = DEFAULT_RULES
    by_team: Mapping[UUID, MetricRules] = field(default_factory=dict)

    def for_team(self, team_id: UUID) -> MetricRules:
        return self.by_team.get(team_id, self.scope)


class MetricRulesResolver:
    """Reads the override layers and resolves effective rules per team."""

    def __init__(
        self,
        overrides: MetricRuleOverridesRepository,
        teams: TeamRepository,
        projects: ProjectRepository,
    ) -> None:
        self._overrides = overrides
        self._teams = teams
        self._projects = projects

    async def resolve(
        self, *, team_id: UUID | None, project_id: UUID | None, item_team_ids: Iterable[UUID]
    ) -> ResolvedRules:
        """Rules for a team or project scope whose items belong to `item_team_ids`."""
        item_teams = set(item_team_ids)
        home_team = team_id if team_id is not None else await self._project_team(project_id)
        # A project scope reads its items' team rules (one team), the workspace
        # rules (several) or its home team's (none); a team scope reads its own.
        # ponytail: a project that turns multi-team after an item moves keeps the
        # history written under its earlier rules until the next rules change or
        # rebuild sync.
        scope_team = home_team
        if team_id is None and len(item_teams) == 1:
            (scope_team,) = item_teams
        wanted = item_teams | ({home_team} if home_team is not None else set())
        org_rows: dict[UUID, RuleOverrides | None] = {}
        warned: list[Mapping[str, object]] = []
        by_team = {tid: await self._team_rules(tid, org_rows, warned) for tid in wanted}
        if scope_team is None:
            scope = DEFAULT_RULES
        elif team_id is None and len(item_teams) > 1:
            scope = await self._workspace_rules(scope_team, org_rows, warned)
        else:
            scope = by_team[scope_team]
        return ResolvedRules(scope=scope, by_team=by_team)

    async def team_rules(self, team_id: UUID) -> MetricRules:
        """The team's effective rules; built-in defaults if stored rules are invalid."""
        return await self._team_rules(team_id, {}, [])

    async def _team_rules(
        self,
        team_id: UUID,
        org_rows: dict[UUID, RuleOverrides | None],
        warned: list[Mapping[str, object]],
    ) -> MetricRules:
        team = await self._teams.get(team_id)
        if team is None:
            return DEFAULT_RULES
        if team.organization_id not in org_rows:
            org_rows[team.organization_id] = await self._overrides.get(team.organization_id)
        rows = (
            org_rows[team.organization_id],
            await self._overrides.get(team.organization_id, team_id=team_id),
        )
        layers = [row.overrides for row in rows if row is not None]
        return resolve_layers(*layers, subject=f"team {team_id}", warned=warned)

    async def _workspace_rules(
        self,
        home_team: UUID,
        org_rows: dict[UUID, RuleOverrides | None],
        warned: list[Mapping[str, object]],
    ) -> MetricRules:
        """The workspace layer alone, for the organization of the project's home team."""
        team = await self._teams.get(home_team)
        if team is None:
            return DEFAULT_RULES
        if team.organization_id not in org_rows:
            org_rows[team.organization_id] = await self._overrides.get(team.organization_id)
        row = org_rows[team.organization_id]
        layers = [row.overrides] if row is not None else []
        return resolve_layers(
            *layers, subject=f"organization {team.organization_id}", warned=warned
        )

    async def _project_team(self, project_id: UUID | None) -> UUID | None:
        if project_id is None:
            return None
        project = await self._projects.get(project_id)
        return project.team_id if project is not None else None
