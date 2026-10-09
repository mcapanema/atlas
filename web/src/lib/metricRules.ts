import type { Organization } from "../api/organizations";
import type {
  MetricRules,
  MetricRulesView,
  RuleChanges,
  RuleName,
  OpenStateType,
  RuleValue,
  RulesScope,
  TypeLabel,
  WorkItemTypeName,
} from "../api/metricRules";
import type { Team } from "../api/teams";

type Control =
  | { kind: "switch" }
  | { kind: "select"; options: { value: string; label: string }[] }
  | { kind: "number"; min: number; max: number; step: number; suffix?: string }
  | { kind: "timezone" }
  | { kind: "labels" }
  | { kind: "names" }
  | { kind: "states" }
  | { kind: "typeLabels" };

export const STATE_TYPE_OPTIONS: { value: OpenStateType; label: string }[] = [
  { value: "triage", label: "Triage" },
  { value: "backlog", label: "Backlog" },
  { value: "unstarted", label: "Todo" },
  { value: "started", label: "In progress" },
];

export const WORK_ITEM_TYPE_OPTIONS: { value: WorkItemTypeName; label: string }[] = [
  { value: "story", label: "story" },
  { value: "task", label: "task" },
  { value: "bug", label: "bug" },
  { value: "spike", label: "spike" },
  { value: "other", label: "other" },
];

/** State types in workflow order — the server's canonical order, so a reorder isn't a change. */
export function canonicalStates(states: OpenStateType[]): OpenStateType[] {
  return STATE_TYPE_OPTIONS.map((option) => option.value).filter((value) => states.includes(value));
}

/** Rule values compare by content: lists and mappings are fresh arrays on every edit. */
export function sameRuleValue(a: RuleValue | null, b: RuleValue | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

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
      {
        name: "count_parent_issues",
        label: "Count parent issues",
        help: "Off: an issue with sub-issues leaves every metric, remaining included; only its sub-issues count. Avoids counting the same work twice.",
        control: { kind: "switch" },
      },
      {
        name: "lead_time_start",
        label: "Lead time starts",
        help: "At creation, or when the item first leaves Triage. Also where pre-start queue time begins. Items never in Triage start at creation.",
        control: {
          kind: "select",
          options: [
            { value: "created", label: "At creation" },
            { value: "triage_exit", label: "When it leaves Triage" },
          ],
        },
      },
      {
        name: "done_then_reopened",
        label: "Done, then moved back to Todo",
        help: "Moved from done back to a not-started state (Todo, Backlog, Triage) without restarting: stays delivered, or counts as open again (remaining, not WIP). A later start keeps the original clock.",
        control: {
          kind: "select",
          options: [
            { value: "delivered", label: "Stays delivered" },
            { value: "reopened", label: "Counts as reopened" },
          ],
        },
      },
      {
        name: "canceled_then_reopened",
        label: "Canceled, then moved back to Todo",
        help: "Moved from canceled back to a not-started state: stays canceled, or counts as open again (remaining, not WIP).",
        control: {
          kind: "select",
          options: [
            { value: "canceled", label: "Stays canceled" },
            { value: "reopened", label: "Counts as reopened" },
          ],
        },
      },
    ],
  },
  {
    title: "Blocked",
    rules: [
      {
        name: "blocked_label_pattern",
        label: "Labels named like 'Blocked'",
        help: "Labels such as Blocked, Blocker: external or Blocking mark an item blocked while applied. Whole words only: 'regras-blockly' doesn't count.",
        control: { kind: "switch" },
      },
      {
        name: "blocked_label_names",
        label: "More blocked labels",
        help: "Further label names that mark an item blocked while applied (any case).",
        control: { kind: "labels" },
      },
      {
        name: "blocked_state_pattern",
        label: "Workflow states named like 'Blocked'",
        help: "An item is blocked while it sits in a workflow state such as Blocked or Blocked by vendor. Whole words only: 'Unblocked' doesn't count.",
        control: { kind: "switch" },
      },
      {
        name: "blocked_state_names",
        label: "More blocked states",
        help: "Further workflow state names an item is blocked while in (any case), e.g. Aguardando cliente.",
        control: { kind: "names" },
      },
      {
        name: "blocked_by_relations",
        label: "Count Linear 'blocked by' relations",
        help: "An item is blocked from when a 'blocked by' relation is added until it is removed or the blocker is done or canceled, and again if the blocker reopens. Linear records relation history from about mid-2026; older relations don't count.",
        control: { kind: "switch" },
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
      {
        name: "health_min_sample",
        label: "Minimum items per component",
        help: "A health component scores only with at least this many items behind it: completions in the window, or items in progress for risk. With fewer it's left out, and a team with no component left reads not scored yet.",
        control: { kind: "number", min: 1, max: 50, step: 1, suffix: "items" },
      },
      weight("weight_predictability", "predictability"),
      weight("weight_efficiency", "efficiency"),
      weight("weight_flow", "flow"),
      weight("weight_stability", "stability"),
      weight("weight_risk", "risk"),
    ],
  },
  {
    title: "Forecast & windows",
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
      {
        name: "remaining_state_types",
        label: "Forecast counts as remaining",
        help: "Open items count toward the completion forecast only in these states. Items created outside Linear always count.",
        control: { kind: "states" },
      },
    ],
  },
  {
    title: "Work item types",
    rules: [
      {
        name: "type_labels",
        label: "Type from labels",
        help: "An item takes the type of the first mapped label it carries; otherwise it stays a task. Drives the type filter on every dashboard.",
        control: { kind: "typeLabels" },
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

function formatListValue(kind: Control["kind"], value: RuleValue): string | undefined {
  if (kind === "labels" || kind === "names") {
    const names = value as string[];
    return names.length ? names.join(", ") : "None";
  }
  if (kind === "states") {
    return STATE_TYPE_OPTIONS.filter((o) => (value as string[]).includes(o.value))
      .map((o) => o.label)
      .join(", ");
  }
  if (kind === "typeLabels") {
    const rows = value as TypeLabel[];
    return rows.length ? rows.map((row) => `${row.label} → ${row.type}`).join(", ") : "None";
  }
  return undefined;
}

export function formatRuleValue(spec: RuleSpec, value: RuleValue): string {
  const { control } = spec;
  const list = formatListValue(control.kind, value);
  if (list !== undefined) return list;
  const scalar = value as string | number | boolean;
  if (control.kind === "switch") return scalar ? "On" : "Off";
  if (control.kind === "select") {
    return control.options.find((option) => option.value === scalar)?.label ?? String(scalar);
  }
  if (control.kind === "number" && control.suffix) return `${String(scalar)} ${control.suffix}`;
  return String(scalar);
}

/** A draft entry equal to the inherited value, with no saved override, is no override at all. */
export function draftValue(
  view: Pick<MetricRulesView, "inherited" | "overrides">,
  name: RuleName,
  value: RuleValue | null,
): RuleValue | null {
  return sameRuleValue(value, view.inherited[name]) && view.overrides[name] == null ? null : value;
}

/** What to PATCH: draft values that differ from the saved overrides (null = inherit). */
export function pendingChanges(saved: Partial<MetricRules>, draft: RuleChanges): RuleChanges {
  const changes: RuleChanges = {};
  for (const name of Object.keys(draft) as RuleName[]) {
    const next = draft[name] ?? null;
    if (!sameRuleValue(next, saved[name] ?? null)) changes[name] = next;
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
