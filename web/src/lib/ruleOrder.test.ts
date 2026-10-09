import { describe, expect, it } from "vitest";

import { orderProblems } from "./ruleOrder";

describe("orderProblems", () => {
  const ordered = {
    healthy_min: 70,
    warning_min: 40,
    stability_best_weeks: 1,
    stability_worst_weeks: 5,
    predictability_floor: 25,
    aging_percentile: 85,
    weight_predictability: 1,
    weight_efficiency: 0,
    weight_flow: 1,
    weight_stability: 1,
    weight_risk: 1,
  };

  it("finds nothing wrong with the built-in rules", () => {
    expect(orderProblems(ordered)).toEqual([]);
  });

  it("names each pair of rules the server would reject", () => {
    expect(orderProblems({ ...ordered, warning_min: 70 })).toEqual([
      "Warning from score must be below Healthy from score.",
    ]);
    expect(orderProblems({ ...ordered, stability_worst_weeks: 1 })).toEqual([
      "Stability: worst WIP must be above Stability: best WIP.",
    ]);
    expect(orderProblems({ ...ordered, predictability_floor: 85 })).toEqual([
      "Predictability: floor hit rate must be below Aging flag percentile.",
    ]);
    expect(
      orderProblems({
        ...ordered,
        weight_predictability: 0,
        weight_flow: 0,
        weight_stability: 0,
        weight_risk: 0,
      }),
    ).toEqual(["At least one health weight must be above 0."]);
  });
});
