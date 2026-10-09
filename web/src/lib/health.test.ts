import { describe, expect, it } from "vitest";

import type { DeliveryHealth } from "../api/metrics";
import { healthFixture } from "../test/fixtures";
import { componentHelp, isAtRisk, weakestComponents } from "./health";

const health = healthFixture as DeliveryHealth;
const withBand = (band: DeliveryHealth["band"]): DeliveryHealth => ({ ...health, band });

describe("isAtRisk", () => {
  it("flags warning and critical bands", () => {
    expect(isAtRisk(withBand("warning"))).toBe(true);
    expect(isAtRisk(withBand("critical"))).toBe(true);
  });

  it("leaves healthy, unscored, and not-yet-loaded teams alone", () => {
    expect(isAtRisk(withBand("healthy"))).toBe(false);
    expect(isAtRisk(withBand(null))).toBe(false);
    expect(isAtRisk(undefined)).toBe(false);
  });
});

describe("weakestComponents", () => {
  it("returns the lowest-scoring components first, capped at count", () => {
    // healthFixture: risk 70, predictability 74, efficiency 78, stability 89, flow 100.
    expect(weakestComponents(health, 2).map((component) => component.name)).toEqual([
      "risk",
      "predictability",
    ]);
  });

  it("leaves the health payload's own order untouched", () => {
    const before = health.components.map((component) => component.name);
    weakestComponents(health, 2);
    expect(health.components.map((component) => component.name)).toEqual(before);
  });

  it("returns nothing when health has no components", () => {
    expect(weakestComponents({ ...health, components: [] }, 2)).toEqual([]);
  });
});

describe("componentHelp", () => {
  it("defines every component the backend scores", () => {
    for (const name of ["predictability", "efficiency", "flow", "stability", "risk"]) {
      expect(componentHelp(name)).toMatch(/\w/);
    }
  });

  it("names risk's fallback limit when nothing completed in the aging history", () => {
    // app/domain/metrics/health.py `_aging_limit`: no completions in the
    // history means the history itself is the aging limit.
    expect(componentHelp("risk")).toMatch(/aging percentile/);
    expect(componentHelp("risk")).toMatch(/nothing completed/);
  });

  it("has no definition for a name it doesn't know", () => {
    expect(componentHelp("cadence")).toBeUndefined();
  });
});
