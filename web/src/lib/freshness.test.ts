import { describe, expect, it } from "vitest";

import { STALE_AFTER_HOURS, stalenessHours } from "./freshness";

describe("stalenessHours", () => {
  it("is null when the scope has no data at all", () => {
    expect(stalenessHours(null, "2026-07-19T02:00:00Z")).toBeNull();
  });

  it("measures the gap between the last record and the window end", () => {
    expect(stalenessHours("2026-07-16T02:00:00Z", "2026-07-19T02:00:00Z")).toBe(72);
  });

  it("is zero for data recorded after the window end", () => {
    expect(stalenessHours("2026-07-19T06:00:00Z", "2026-07-19T02:00:00Z")).toBe(0);
  });

  it("treats a day-old sync as the staleness threshold", () => {
    expect(STALE_AFTER_HOURS).toBe(24);
  });
});
