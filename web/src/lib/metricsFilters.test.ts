import { describe, expect, it } from "vitest";

import {
  applyFiltersToSearchParams,
  filtersFromSearchParams,
  isDefaultFilters,
  periodText,
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
    expect(filtersFromSearchParams(new URLSearchParams("start=2026-06-01&end=2026-06-30"))).toEqual(
      { start: "2026-06-01", end: "2026-06-30" },
    );
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

describe("periodText", () => {
  const window = { window_start: "2026-06-01T00:00:00Z", window_end: "2026-07-01T00:00:00Z" };

  it("names a custom range by its own dates, window or not", () => {
    const filters = { start: "2026-05-01", end: "2026-05-31" };
    expect(periodText(filters, window)).toBe("01-05-2026 – 31-05-2026");
    expect(periodText(filters, undefined)).toBe("01-05-2026 – 31-05-2026");
  });

  it("names a preset by its length and the window the API resolved", () => {
    expect(periodText({ windowDays: 90 }, window)).toBe("Last 90 days · 01-06-2026 – 01-07-2026");
    expect(periodText({}, window)).toBe("Last 30 days · 01-06-2026 – 01-07-2026");
  });

  it("is null for a preset until the window is known", () => {
    expect(periodText({}, undefined)).toBeNull();
  });
});
