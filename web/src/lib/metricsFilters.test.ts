import { describe, expect, it } from "vitest";

import {
  applyFiltersToSearchParams,
  filtersFromSearchParams,
  isDefaultFilters,
  windowLabel,
} from "./metricsFilters";

describe("filtersFromSearchParams", () => {
  it("reads window, range, types and excluded states", () => {
    const params = new URLSearchParams(
      "team=t1&window=90&types=story,bug&xstates=canceled,duplicate",
    );
    expect(filtersFromSearchParams(params)).toEqual({
      windowDays: 90,
      types: ["story", "bug"],
      excludeStates: ["canceled", "duplicate"],
    });
  });

  it("reads a custom range only when both bounds are present", () => {
    expect(
      filtersFromSearchParams(new URLSearchParams("start=2026-06-01&end=2026-06-30")),
    ).toEqual({ start: "2026-06-01", end: "2026-06-30" });
    expect(filtersFromSearchParams(new URLSearchParams("start=2026-06-01"))).toEqual({});
  });
});

describe("applyFiltersToSearchParams", () => {
  it("round-trips and preserves unrelated params", () => {
    const params = new URLSearchParams("team=t1&window=30");
    const filters = { start: "2026-06-01", end: "2026-06-30", types: ["bug"] };
    applyFiltersToSearchParams(params, filters);
    expect(params.get("team")).toBe("t1");
    expect(params.get("window")).toBeNull(); // range replaces the preset
    expect(filtersFromSearchParams(params)).toEqual(filters);
  });
});

describe("windowLabel", () => {
  it("names the preset or the default", () => {
    expect(windowLabel({}, 30)).toBe("30d");
    expect(windowLabel({ windowDays: 90 }, 30)).toBe("90d");
  });

  it("names a custom range by its dates", () => {
    expect(windowLabel({ start: "2026-06-01", end: "2026-06-30" }, 30)).toMatch(/–/);
  });
});

describe("isDefaultFilters", () => {
  it("is true only for the untouched 30d view", () => {
    expect(isDefaultFilters({})).toBe(true);
    expect(isDefaultFilters({ windowDays: 30 })).toBe(true);
    expect(isDefaultFilters({ windowDays: 90 })).toBe(false);
    expect(isDefaultFilters({ start: "2026-06-01", end: "2026-06-30" })).toBe(false);
    expect(isDefaultFilters({ types: ["bug"] })).toBe(false);
    expect(isDefaultFilters({ excludeStates: ["canceled"] })).toBe(false);
  });
});
