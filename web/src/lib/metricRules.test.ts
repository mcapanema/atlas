import { describe, expect, it } from "vitest";

import { teamFixture } from "../test/fixtures";
import {
  RULE_GROUPS,
  formatRuleValue,
  pendingChanges,
  recomputeOrganization,
  scopeFromParams,
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
