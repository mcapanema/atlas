import { describe, expect, it } from "vitest";

import type { MetricRules } from "../api/metricRules";
import {
  RULE_GROUPS,
  canonicalStates,
  draftValue,
  formatRuleValue,
  pendingChanges,
  sameRuleValue,
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

  it("reads a date rule as a calendar day, or not set", () => {
    expect(formatRuleValue(ruleSpec("tracked_since"), "2026-08-20")).toBe("20-08-2026");
    expect(formatRuleValue(ruleSpec("tracked_since"), null)).toBe("Not set");
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
    expect(formatRuleValue(ruleSpec("wait_state_names"), [])).toBe("None");
    expect(formatRuleValue(ruleSpec("wait_state_names"), ["In Review", "Waiting for Deploy"])).toBe(
      "In Review, Waiting for Deploy",
    );
    expect(formatRuleValue(ruleSpec("health_min_sample"), 3)).toBe("3 items");
    expect(formatRuleValue(ruleSpec("sprint_length_days"), 14)).toBe("14 days");
    expect(formatRuleValue(ruleSpec("working_days"), [1, 2, 3, 4, 5])).toBe(
      "Mon, Tue, Wed, Thu, Fri",
    );
    expect(formatRuleValue(ruleSpec("working_days"), [1, 2, 3, 4, 5, 6, 7])).toBe("Every day");
    expect(formatRuleValue(ruleSpec("holidays"), [])).toBe("None");
    expect(formatRuleValue(ruleSpec("holidays"), ["2026-01-01", "2026-12-25"])).toBe(
      "01-01-2026, 25-12-2026",
    );
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

describe("rules that feed predictability", () => {
  it.each(["aging_percentile", "aging_history_days", "health_min_sample"])(
    "%s says it shapes the predictability service level",
    (name) => {
      expect(ruleSpec(name).help).toMatch(/predictability/i);
    },
  );
});
