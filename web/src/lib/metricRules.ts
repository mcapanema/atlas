import type { Organization } from "../api/organizations";
import type {
  MetricRules,
  MetricRulesView,
  RuleChanges,
  RuleName,
  RuleValue,
  RulesScope,
} from "../api/metricRules";
import type { Team } from "../api/teams";

type Control =
  | { kind: "switch" }
  | { kind: "select"; options: { value: string; label: string }[] }
  | { kind: "number"; min: number; max: number; step: number; suffix?: string }
  | { kind: "timezone" };

export interface RuleSpec {
  name: RuleName;
  label: string;
  help: string;
  control: Control;
}

export interface RuleGroup {
  title: string;
  rules: RuleSpec[];
}

const WEIGHT_HELP = "How much this component counts in the overall score. 0 leaves it out.";

function weight(name: RuleName, component: string): RuleSpec {
  return {
    name,
    label: `Weight: ${component}`,
    help: WEIGHT_HELP,
    control: { kind: "number", min: 0, max: 10, step: 0.5 },
  };
}

export const RULE_GROUPS: RuleGroup[] = [
  {
    title: "Lifecycle",
    rules: [
      {
        name: "exclude_born_done",
        label: "Leave out items created already done",
        help: "Items logged straight into a done state (retro-logged records) are excluded from every metric, forecast remaining included.",
        control: { kind: "switch" },
      },
      {
        name: "move_back_ends_wip",
        label: "Moving back to backlog ends WIP",
        help: "An item that leaves an in-progress state for a not-started one stops counting as work in progress.",
        control: { kind: "switch" },
      },
      {
        name: "restart_clock_after_move_back",
        label: "Restart the clock after a move-back",
        help: 'When an item moved back to backlog is started again, cycle time and aging count from the restart; the parked time becomes queue time. Applies after a move-back only while "Moving back to backlog ends WIP" is on, and always after a cancel. A reopen after done never restarts the clock.',
        control: { kind: "switch" },
      },
      {
        name: "reopen_completion",
        label: "Reopened after done: measure to",
        help: "For an item completed, reopened and completed again: its last completion, or its first.",
        control: {
          kind: "select",
          options: [
            { value: "last", label: "Last completion" },
            { value: "first", label: "First completion" },
          ],
        },
      },
      {
        name: "done_then_canceled",
        label: "Done, then canceled",
        help: "Whether an item canceled after reaching done still counts as delivered.",
        control: {
          kind: "select",
          options: [
            { value: "delivered", label: "Stays delivered" },
            { value: "canceled", label: "Counts as canceled" },
          ],
        },
      },
    ],
  },
  {
    title: "Health",
    rules: [
      {
        name: "healthy_min",
        label: "Healthy from score",
        help: "An overall health score at or above this reads healthy.",
        control: { kind: "number", min: 1, max: 100, step: 1 },
      },
      {
        name: "warning_min",
        label: "Warning from score",
        help: "At or above this (and below healthy) reads warning; below it, critical.",
        control: { kind: "number", min: 0, max: 99, step: 1 },
      },
      {
        name: "predictability_worst_ratio",
        label: "Predictability: worst lead-time spread",
        help: "Lead-time p95 equal to p50 scores 100; at this multiple of p50 it scores 0.",
        control: { kind: "number", min: 1.1, max: 20, step: 0.1, suffix: "× p50" },
      },
      {
        name: "stability_best_weeks",
        label: "Stability: best WIP",
        help: "WIP worth this many weeks of throughput or less scores 100.",
        control: { kind: "number", min: 0, max: 52, step: 0.5, suffix: "weeks" },
      },
      {
        name: "stability_worst_weeks",
        label: "Stability: worst WIP",
        help: "WIP worth this many weeks of throughput or more scores 0.",
        control: { kind: "number", min: 0.1, max: 52, step: 0.5, suffix: "weeks" },
      },
      {
        name: "aging_percentile",
        label: "Aging flag percentile",
        help: "In-progress items older than this percentile of completed cycle times are flagged as aging; it also feeds the health risk score.",
        control: { kind: "number", min: 50, max: 99, step: 1 },
      },
      weight("weight_predictability", "predictability"),
      weight("weight_efficiency", "efficiency"),
      weight("weight_flow", "flow"),
      weight("weight_stability", "stability"),
      weight("weight_risk", "risk"),
    ],
  },
  {
    title: "Calendar & windows",
    rules: [
      {
        name: "timezone",
        label: "Time zone",
        help: "Day boundaries for date ranges and the cumulative flow chart.",
        control: { kind: "timezone" },
      },
      {
        name: "daily_bucket_max_days",
        label: "Daily throughput bars up to",
        help: "Windows up to this many days chart throughput per day; longer windows per week.",
        control: { kind: "number", min: 1, max: 90, step: 1, suffix: "days" },
      },
      {
        name: "forecast_history_days",
        label: "Forecast history",
        help: "How many recent days of throughput the completion forecast samples from.",
        control: { kind: "number", min: 7, max: 365, step: 1, suffix: "days" },
      },
    ],
  },
];

let zones: { value: string; label: string }[] | undefined;

/** Every IANA zone the browser knows, UTC first. */
export function timeZoneOptions() {
  zones ??= ["UTC", ...Intl.supportedValuesOf("timeZone").filter((zone) => zone !== "UTC")].map(
    (zone) => ({ value: zone, label: zone }),
  );
  return zones;
}

export function formatRuleValue(spec: RuleSpec, value: RuleValue): string {
  const { control } = spec;
  if (control.kind === "switch") return value ? "On" : "Off";
  if (control.kind === "select") {
    return control.options.find((option) => option.value === value)?.label ?? String(value);
  }
  if (control.kind === "number" && control.suffix) return `${String(value)} ${control.suffix}`;
  return String(value);
}

/** A draft entry equal to the inherited value, with no saved override, is no override at all. */
export function draftValue(
  view: Pick<MetricRulesView, "inherited" | "overrides">,
  name: RuleName,
  value: RuleValue | null,
): RuleValue | null {
  return value === view.inherited[name] && view.overrides[name] == null ? null : value;
}

/** What to PATCH: draft values that differ from the saved overrides (null = inherit). */
export function pendingChanges(saved: Partial<MetricRules>, draft: RuleChanges): RuleChanges {
  const changes: RuleChanges = {};
  for (const name of Object.keys(draft) as RuleName[]) {
    const next = draft[name] ?? null;
    if (next !== (saved[name] ?? null)) changes[name] = next;
  }
  return changes;
}

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

/** The organization whose history a recompute for `scope` rewrites. */
export function recomputeOrganization(
  scope: RulesScope | undefined,
  teams: Team[] | undefined,
): string | undefined {
  if (scope?.kind === "team") return teams?.find((team) => team.id === scope.id)?.organization_id;
  return scope?.id;
}
