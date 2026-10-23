import type { RulesScope } from "../api/metricRules";
import type { Organization } from "../api/organizations";
import type { Team } from "../api/teams";

export function scopeFromParams(
  params: URLSearchParams,
  fallbackOrganizationId: string | undefined,
): RulesScope | undefined {
  const team = params.get("team");
  if (team) return { kind: "team", id: team };
  const organization = params.get("org") ?? fallbackOrganizationId;
  return organization ? { kind: "organization", id: organization } : undefined;
}

export function scopeValue(scope: RulesScope | undefined): string | undefined {
  return scope && `${scope.kind}:${scope.id}`;
}

export function scopeParams(value: string): Record<string, string> {
  const [kind, id = ""] = value.split(":");
  return kind === "team" ? { team: id } : { org: id };
}

export function scopeOptions(organizations: Organization[], teams: Team[]) {
  return [
    ...organizations.map((org) => ({
      value: `organization:${org.id}`,
      label: `Workspace default — ${org.name}`,
    })),
    ...teams.map((team) => ({ value: `team:${team.id}`, label: team.name })),
  ];
}

/** The organization a workspace scope names; undefined for a team (rules travel per organization). */
export function workspaceOrganization(
  scope: RulesScope | undefined,
  organizations: Organization[],
): Organization | undefined {
  return scope?.kind === "organization"
    ? organizations.find((org) => org.id === scope.id)
    : undefined;
}

/** The organization whose history a recompute for `scope` rewrites. */
export function recomputeOrganization(
  scope: RulesScope | undefined,
  teams: Team[] | undefined,
): string | undefined {
  if (scope?.kind === "team") return teams?.find((team) => team.id === scope.id)?.organization_id;
  return scope?.id;
}
