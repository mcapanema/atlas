"""Use cases for the per-team metric rules.

Read the layers (built-in, workspace, team), change them, and say which
scopes' snapshot history a change invalidates. The history rewrite itself
runs in Presentation's background runner; this service only records its
status on the organization's row.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from uuid import UUID

from app.application.metric_rules.resolver import resolve_layers
from app.application.metric_rules.sharing import SharedRules, SharedTeamRules, match_teams
from app.domain._time import utcnow
from app.domain.metric_rules.entities import (
    DEFAULT_RULES,
    METRIC_RULE_NAMES,
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

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class TeamRulesSummary:
    """A team's effective rules, and whether a metric rule differs from its workspace default."""

    effective: MetricRules
    custom: bool


@dataclass(frozen=True)
class RulesImport:
    """An imported rules file: the saved change, and which of its teams landed."""

    change: RulesChange
    # Local team names, sorted.
    imported_teams: tuple[str, ...]
    # The file's names for teams matching none here, in file order.
    skipped_teams: tuple[str, ...]


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
    """The metric rules that differ; a meeting rule (MEETING_RULES) changes no metric."""
    return {name for name in METRIC_RULE_NAMES if getattr(before, name) != getattr(after, name)}


def _reject_unknown(changes: Mapping[str, object | None]) -> None:
    unknown = unknown_rule_names(changes)
    if unknown:
        raise ValueError(f"Unknown metric rule(s): {', '.join(unknown)}")


def _check_team(
    team: Team,
    before: Mapping[str, object],
    workspace: Mapping[str, object],
    own: Mapping[str, object],
) -> None:
    """Reject a workspace change that newly invalidates the team's rules.

    A team already invalid under the `before` workspace (corrupt or legacy
    JSON) isn't the change's doing: it is skipped with a warning, so it can't
    block every workspace update. If the stored workspace layer is itself
    corrupt, every team counts as already invalid, so a fixing change is
    accepted with only a warning — consistent with the resolver's built-in
    fallback for those teams.
    """
    try:
        resolve_rules(workspace, own)
    except ValueError as exc:
        try:
            resolve_rules(before, own)
        except ValueError as earlier:
            logger.warning(
                "Team %s's stored metric rules were already invalid: %s", team.name, earlier
            )
            return
        raise ValueError(f"Conflicts with team {team.name}'s own rules: {exc}") from exc


def _imported_layer(
    team: Team,
    before: Mapping[str, object],
    workspace: Mapping[str, object],
    own: Mapping[str, object],
    entry: SharedTeamRules | None,
) -> dict[str, object]:
    """The team's layer after an import; raises ValueError if it can't resolve.

    A team the file names takes the file's layer; any other keeps its own,
    which must still resolve under the imported workspace.
    """
    if entry is None:
        _check_team(team, before, workspace, own)
        return dict(own)
    layer = dict(entry.overrides)
    try:
        resolve_rules(workspace, layer)
    except ValueError as exc:
        raise ValueError(f"Team {team.name}: {exc}") from exc
    return layer


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
        team_layers = await self._checked_team_layers(organization_id, teams, row.overrides, layer)
        before = resolve_layers(row.overrides, subject=f"organization {organization_id}")
        changed = _changed(before, after)
        affected = [t.id for t in teams if changed - set(team_layers.get(t.id, {}))]
        scopes = await self._scopes_for(affected)
        if layer != row.overrides:  # a same-value change must not bump "last edited"
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
        if layer != row.overrides:  # a same-value change must not bump "last edited"
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

    async def export_rules(self, organization_id: UUID) -> SharedRules | None:
        """The workspace layer and every team's non-empty layer, teams by name."""
        if await self._organizations.get(organization_id) is None:
            return None
        rows = await self._overrides.list_for_organization(organization_id)
        workspace = next((dict(r.overrides) for r in rows if r.team_id is None), {})
        own = {r.team_id: dict(r.overrides) for r in rows if r.team_id is not None and r.overrides}
        teams = sorted(
            (t for t in await self._organization_teams(organization_id) if t.id in own),
            key=lambda t: t.name,
        )
        return SharedRules(
            workspace=workspace,
            teams=tuple(SharedTeamRules(t.name, t.external_id, own[t.id]) for t in teams),
        )

    async def import_rules(self, organization_id: UUID, shared: SharedRules) -> RulesImport | None:
        """Replace the workspace layer and each matched team's; nothing is saved on ValueError."""
        if await self._organizations.get(organization_id) is None:
            return None
        for layer in (shared.workspace, *(entry.overrides for entry in shared.teams)):
            _reject_unknown(layer)
        teams = await self._organization_teams(organization_id)
        matched, skipped = match_teams(shared.teams, teams)
        rows = await self._overrides.list_for_organization(organization_id)
        workspace_row = next((r for r in rows if r.team_id is None), None)
        team_rows = {r.team_id: r for r in rows if r.team_id is not None}
        before = _layer(workspace_row)
        workspace = dict(shared.workspace)
        after = resolve_rules(workspace)
        layers = {
            t.id: _imported_layer(
                t, before, workspace, _layer(team_rows.get(t.id)), matched.get(t.id)
            )
            for t in teams
        }
        changed = [
            t.id
            for t in teams
            if _changed(
                resolve_layers(before, _layer(team_rows.get(t.id)), subject=f"team {t.id}"),
                resolve_rules(workspace, layers[t.id]),
            )
        ]
        await self._replace_layer(workspace_row, organization_id, None, workspace)
        for team_id in matched:
            await self._replace_layer(
                team_rows.get(team_id), organization_id, team_id, layers[team_id]
            )
        scopes = await self._scopes_for(changed)
        status = await self._mark_running(organization_id) if scopes else _status(workspace_row)
        view = RulesView(
            built_in=DEFAULT_RULES,
            inherited=DEFAULT_RULES,
            overrides=workspace,
            effective=after,
            recompute=status,
        )
        return RulesImport(
            change=RulesChange(view=view, organization_id=organization_id, scopes=scopes),
            imported_teams=tuple(sorted(t.name for t in teams if t.id in matched)),
            skipped_teams=skipped,
        )

    async def _replace_layer(
        self,
        row: RuleOverrides | None,
        organization_id: UUID,
        team_id: UUID | None,
        layer: dict[str, object],
    ) -> None:
        """Save `layer` as the row's overrides, only when they differ."""
        if row is None:
            if layer:
                await self._overrides.save(
                    RuleOverrides(organization_id=organization_id, team_id=team_id, overrides=layer)
                )
        elif layer != dict(row.overrides):  # a same-value import must not bump "last edited"
            await self._overrides.save(replace(row, overrides=layer, updated_at=utcnow()))

    async def organization_scopes(self, organization_id: UUID) -> tuple[ScopeRef, ...]:
        """Every team of the organization and every project they own."""
        return await self._scopes_for(
            [t.id for t in await self._organization_teams(organization_id)]
        )

    async def team_summaries(self, teams: list[Team]) -> dict[UUID, TeamRulesSummary]:
        """Each team's effective rules and custom flag; one overrides read per organization."""
        summaries: dict[UUID, TeamRulesSummary] = {}
        for organization_id in {team.organization_id for team in teams}:
            rows = await self._overrides.list_for_organization(organization_id)
            workspace = next((dict(r.overrides) for r in rows if r.team_id is None), {})
            own = {r.team_id: dict(r.overrides) for r in rows if r.team_id is not None}
            default = resolve_layers(workspace, subject=f"organization {organization_id}")
            for team in (t for t in teams if t.organization_id == organization_id):
                effective = (
                    resolve_layers(workspace, own[team.id], subject=f"team {team.id}")
                    if team.id in own
                    else default
                )
                summaries[team.id] = TeamRulesSummary(
                    effective=effective, custom=bool(_changed(default, effective))
                )
        return summaries

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
        self,
        organization_id: UUID,
        teams: list[Team],
        before: Mapping[str, object],
        workspace: Mapping[str, object],
    ) -> dict[UUID, dict[str, object]]:
        """Each team's own layer; raises ValueError if `workspace` newly conflicts with one."""
        team_layers = {
            r.team_id: dict(r.overrides)
            for r in await self._overrides.list_for_organization(organization_id)
            if r.team_id is not None
        }
        for team in teams:
            _check_team(team, before, workspace, team_layers.get(team.id, {}))
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
