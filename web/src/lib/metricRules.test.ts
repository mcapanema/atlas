import { describe, expect, it } from "vitest";

import { teamFixture } from "../test/fixtures";
import type { MetricRules } from "../api/metricRules";
import {
  RULE_GROUPS,
  canonicalStates,
  draftValue,
  formatRuleValue,
  pendingChanges,
  recomputeOrganization,
  scopeFromParams,
  sameRuleValue,
  scopeParams,
  type RuleSpec,
} from "./metricRules";

function ruleSpec(name: string): RuleSpec {
  const found = RULE_GROUPS.flatMap((group) => group.rules).find((rule) => rule.name === name);
  if (!found) throw new Error(`no rule ${name}`);
  return found;
}

describe("pendingChanges", () => {
  it("keeps only values that differ from what is saved", () => {
    expect(
      pendingChanges(
        { aging_percentile: 70 },
        { aging_percentile: 70, healthy_min: 80, timezone: null },
      ),
    ).toEqual({ healthy_min: 80 });
  });

  it("sends null to make a saved override inherit again", () => {
    expect(pendingChanges({ aging_percentile: 70 }, { aging_percentile: null })).toEqual({
      aging_percentile: null,
    });
  });
});

describe("formatRuleValue", () => {
  it("reads switches, choices and units", () => {
    expect(formatRuleValue(ruleSpec("move_back_ends_wip"), true)).toBe("On");
    expect(formatRuleValue(ruleSpec("reopen_completion"), "first")).toBe("First completion");
    expect(formatRuleValue(ruleSpec("forecast_history_days"), 90)).toBe("90 days");
    expect(formatRuleValue(ruleSpec("timezone"), "UTC")).toBe("UTC");
  });
});

describe("scope helpers", () => {
  it("prefers a team, then the org param, then the first organization", () => {
    expect(scopeFromParams(new URLSearchParams("team=t1&org=o1"), "o0")).toEqual({
      kind: "team",
      id: "t1",
    });
    expect(scopeFromParams(new URLSearchParams("org=o1"), "o0")).toEqual({
      kind: "organization",
      id: "o1",
    });
    expect(scopeFromParams(new URLSearchParams(), "o0")).toEqual({
      kind: "organization",
      id: "o0",
    });
    expect(scopeFromParams(new URLSearchParams(), undefined)).toBeUndefined();
  });

  it("maps a picker value to search params", () => {
    expect(scopeParams("team:t1")).toEqual({ team: "t1" });
    expect(scopeParams("organization:o1")).toEqual({ org: "o1" });
  });

  it("finds the organization whose history a scope's recompute rewrites", () => {
    const team = { ...teamFixture, has_custom_rules: false };
    expect(recomputeOrganization({ kind: "team", id: team.id }, [team])).toBe(team.organization_id);
    expect(recomputeOrganization({ kind: "organization", id: "o1" }, undefined)).toBe("o1");
  });
});

describe("list-valued rules", () => {
  it("treats an equal list as no override", () => {
    const inherited = { blocked_label_names: ["Blocked"] } as unknown as MetricRules;
    const view = { inherited, overrides: {} };
    expect(draftValue(view, "blocked_label_names", ["Blocked"])).toBeNull();
    expect(
      pendingChanges({ blocked_label_names: ["Blocked"] }, { blocked_label_names: ["Blocked"] }),
    ).toEqual({});
  });

  it("orders state types canonically so a reorder isn't a change", () => {
    expect(canonicalStates(["started", "unstarted"])).toEqual(["unstarted", "started"]);
    expect(sameRuleValue(["unstarted", "started"], canonicalStates(["started", "unstarted"]))).toBe(
      true,
    );
  });

  it("formats list values for the inherited hint", () => {
    expect(formatRuleValue(ruleSpec("blocked_state_names"), [])).toBe("None");
    expect(
      formatRuleValue(ruleSpec("blocked_state_names"), ["Blocked", "Aguardando cliente"]),
    ).toBe("Blocked, Aguardando cliente");
    expect(formatRuleValue(ruleSpec("health_min_sample"), 3)).toBe("3 items");
    expect(formatRuleValue(ruleSpec("blocked_label_names"), [])).toBe("None");
    expect(formatRuleValue(ruleSpec("blocked_label_names"), ["Blocked", "On hold"])).toBe(
      "Blocked, On hold",
    );
    expect(formatRuleValue(ruleSpec("remaining_state_types"), ["unstarted", "started"])).toBe(
      "Todo, In progress",
    );
    expect(formatRuleValue(ruleSpec("type_labels"), [{ label: "Bug", type: "bug" }])).toBe(
      "Bug → bug",
    );
  });
});
