"""Use cases for the per-team metric rules.

Read the layers (built-in, workspace, team), change them, and say which
scopes' snapshot history a change invalidates. The history rewrite itself
runs in Presentation's background runner; this service only records its
status on the organization's row.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from uuid import UUID

from app.application.metric_rules.resolver import resolve_layers
from app.domain._time import utcnow
from app.domain.metric_rules.entities import (
    DEFAULT_RULES,
    RULE_NAMES,
    MetricRules,
    RecomputeStatus,
    RuleOverrides,
    resolve_rules,
    unknown_rule_names,
)
from app.domain.metric_rules.repository import MetricRuleOverridesRepository
from app.domain.organizations.repository import OrganizationRepository
from app.domain.projects.repository import ProjectRepository
from app.domain.teams.entities import Team
from app.domain.teams.repository import TeamRepository


@dataclass(frozen=True)
class ScopeRef:
    """A team or project scope whose snapshot history may need a recompute."""

    team_id: UUID | None = None
    project_id: UUID | None = None


@dataclass(frozen=True)
class RulesView:
    """One layer as the settings page shows it."""

    built_in: MetricRules
    inherited: MetricRules
    overrides: Mapping[str, object]
    effective: MetricRules
    recompute: RecomputeStatus


@dataclass(frozen=True)
class RulesChange:
    """A saved change: the new view, and the scopes whose history it invalidated."""

    view: RulesView
    organization_id: UUID
    scopes: tuple[ScopeRef, ...]


def _layer(row: RuleOverrides | None) -> dict[str, object]:
    return dict(row.overrides) if row is not None else {}


def _status(row: RuleOverrides | None) -> RecomputeStatus:
    return row.recompute if row is not None else RecomputeStatus()


def _apply(layer: Mapping[str, object], changes: Mapping[str, object | None]) -> dict[str, object]:
    """`layer` with `changes` applied: a value overrides, None removes (inherit again)."""
    updated = dict(layer)
    for name, value in changes.items():
        if value is None:
            updated.pop(name, None)
        else:
            updated[name] = value
    return updated


def _changed(before: MetricRules, after: MetricRules) -> set[str]:
    return {name for name in RULE_NAMES if getattr(before, name) != getattr(after, name)}


def _reject_unknown(changes: Mapping[str, object | None]) -> None:
    unknown = unknown_rule_names(changes)
    if unknown:
        raise ValueError(f"Unknown metric rule(s): {', '.join(unknown)}")


def _check_team(team: Team, workspace: Mapping[str, object], own: Mapping[str, object]) -> None:
    try:
        resolve_rules(workspace, own)
    except ValueError as exc:
        raise ValueError(f"Conflicts with team {team.name}'s own rules: {exc}") from exc


class MetricRulesService:
    """Application use cases for the metric-rule layers."""

    def __init__(
        self,
        overrides: MetricRuleOverridesRepository,
        organizations: OrganizationRepository,
        teams: TeamRepository,
        projects: ProjectRepository,
    ) -> None:
        self._overrides = overrides
        self._organizations = organizations
        self._teams = teams
        self._projects = projects

    async def organization_view(self, organization_id: UUID) -> RulesView | None:
        if await self._organizations.get(organization_id) is None:
            return None
        row = await self._overrides.get(organization_id)
        layer = _layer(row)
        return RulesView(
            built_in=DEFAULT_RULES,
            inherited=DEFAULT_RULES,
            overrides=layer,
            effective=resolve_layers(layer, subject=f"organization {organization_id}"),
            recompute=_status(row),
        )

    async def team_view(self, team_id: UUID) -> RulesView | None:
        team = await self._teams.get(team_id)
        if team is None:
            return None
        workspace_row = await self._overrides.get(team.organization_id)
        workspace = _layer(workspace_row)
        own = _layer(await self._overrides.get(team.organization_id, team_id=team_id))
        subject = f"team {team_id}"
        return RulesView(
            built_in=DEFAULT_RULES,
            inherited=resolve_layers(workspace, subject=subject),
            overrides=own,
            effective=resolve_layers(workspace, own, subject=subject),
            recompute=_status(workspace_row),
        )

    async def update_organization(
        self, organization_id: UUID, changes: Mapping[str, object | None]
    ) -> RulesChange | None:
        """Change the workspace default; teams overriding a changed rule are untouched."""
        if await self._organizations.get(organization_id) is None:
            return None
        _reject_unknown(changes)
        row = await self._overrides.get(organization_id) or RuleOverrides(
            organization_id=organization_id
        )
        layer = _apply(row.overrides, changes)
        after = resolve_rules(layer)
        teams = await self._organization_teams(organization_id)
        team_layers = await self._checked_team_layers(organization_id, teams, layer)
        before = resolve_layers(row.overrides, subject=f"organization {organization_id}")
        changed = _changed(before, after)
        affected = [t.id for t in teams if changed - set(team_layers.get(t.id, {}))]
        scopes = await self._scopes_for(affected)
        await self._overrides.save(replace(row, overrides=layer, updated_at=utcnow()))
        status = await self._mark_running(organization_id) if scopes else row.recompute
        view = RulesView(
            built_in=DEFAULT_RULES,
            inherited=DEFAULT_RULES,
            overrides=layer,
            effective=after,
            recompute=status,
        )
        return RulesChange(view=view, organization_id=organization_id, scopes=scopes)

    async def update_team(
        self, team_id: UUID, changes: Mapping[str, object | None]
    ) -> RulesChange | None:
        """Change one team's overrides; its history (and its projects') is invalidated."""
        team = await self._teams.get(team_id)
        if team is None:
            return None
        _reject_unknown(changes)
        workspace_row = await self._overrides.get(team.organization_id)
        workspace = _layer(workspace_row)
        row = await self._overrides.get(team.organization_id, team_id=team_id) or RuleOverrides(
            organization_id=team.organization_id, team_id=team_id
        )
        layer = _apply(row.overrides, changes)
        after = resolve_rules(workspace, layer)
        await self._overrides.save(replace(row, overrides=layer, updated_at=utcnow()))
        before = resolve_layers(workspace, row.overrides, subject=f"team {team_id}")
        scopes = await self._scopes_for([team_id]) if _changed(before, after) else ()
        status = (
            await self._mark_running(team.organization_id) if scopes else _status(workspace_row)
        )
        view = RulesView(
            built_in=DEFAULT_RULES,
            inherited=resolve_layers(workspace, subject=f"team {team_id}"),
            overrides=layer,
            effective=after,
            recompute=status,
        )
        return RulesChange(view=view, organization_id=team.organization_id, scopes=scopes)

    async def organization_scopes(self, organization_id: UUID) -> tuple[ScopeRef, ...]:
        """Every team of the organization and every project they own."""
        return await self._scopes_for(
            [t.id for t in await self._organization_teams(organization_id)]
        )

    async def custom_team_ids(self, teams: list[Team]) -> set[UUID]:
        """Teams whose effective rules differ from their workspace default."""
        custom: set[UUID] = set()
        for organization_id in {team.organization_id for team in teams}:
            rows = await self._overrides.list_for_organization(organization_id)
            workspace = next((dict(r.overrides) for r in rows if r.team_id is None), {})
            default = resolve_layers(workspace, subject=f"organization {organization_id}")
            for row in rows:
                if row.team_id is None:
                    continue
                own = resolve_layers(workspace, row.overrides, subject=f"team {row.team_id}")
                if own != default:
                    custom.add(row.team_id)
        return custom

    async def start_recompute(self, organization_id: UUID) -> None:
        await self._mark_running(organization_id)

    async def finish_recompute(self, organization_id: UUID, *, error: str | None) -> None:
        row = await self._overrides.get(organization_id)
        status = RecomputeStatus(
            state="failed" if error is not None else "idle",
            started_at=_status(row).started_at,
            finished_at=utcnow(),
            error=error,
        )
        await self._overrides.save_recompute(organization_id, status)

    async def running_organizations(self) -> list[UUID]:
        return [row.organization_id for row in await self._overrides.list_recomputing()]

    async def _mark_running(self, organization_id: UUID) -> RecomputeStatus:
        status = RecomputeStatus(state="running", started_at=utcnow())
        await self._overrides.save_recompute(organization_id, status)
        return status

    async def _checked_team_layers(
        self, organization_id: UUID, teams: list[Team], workspace: Mapping[str, object]
    ) -> dict[UUID, dict[str, object]]:
        """Each team's own layer; raises ValueError if `workspace` conflicts with one."""
        team_layers = {
            r.team_id: dict(r.overrides)
            for r in await self._overrides.list_for_organization(organization_id)
            if r.team_id is not None
        }
        for team in teams:
            _check_team(team, workspace, team_layers.get(team.id, {}))
        return team_layers

    async def _organization_teams(self, organization_id: UUID) -> list[Team]:
        return [t for t in await self._teams.list() if t.organization_id == organization_id]

    async def _scopes_for(self, team_ids: list[UUID]) -> tuple[ScopeRef, ...]:
        # ponytail: a project is recomputed with the team that owns it; a
        # project holding another team's items isn't refreshed when that
        # other team's rules change. Recompute every project containing the
        # team's items if mixed projects ever matter.
        if not team_ids:
            return ()
        wanted = set(team_ids)
        projects = [p for p in await self._projects.list() if p.team_id in wanted]
        return tuple(ScopeRef(team_id=t) for t in team_ids) + tuple(
            ScopeRef(project_id=p.id) for p in projects
        )
