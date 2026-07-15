import { describe, expect, it } from "vitest";

import { metricsParams } from "./metrics";

describe("metricsParams", () => {
  it("returns null without a scope", () => {
    expect(metricsParams({})).toBeNull();
  });

  it("emits the scope alone by default", () => {
    expect(metricsParams({ teamId: "t1" })).toBe("team_id=t1");
    expect(metricsParams({ projectId: "p1" })).toBe("project_id=p1");
  });

  it("emits window_days for a preset window", () => {
    expect(metricsParams({ teamId: "t1" }, { windowDays: 90 })).toBe(
      "team_id=t1&window_days=90",
    );
  });

  it("prefers an explicit range over window_days", () => {
    expect(
      metricsParams(
        { teamId: "t1" },
        { windowDays: 90, start: "2026-06-01", end: "2026-06-30" },
      ),
    ).toBe("team_id=t1&start=2026-06-01&end=2026-06-30");
  });

  it("repeats types and exclude_states", () => {
    expect(
      metricsParams(
        { teamId: "t1" },
        { types: ["story", "bug"], excludeStates: ["canceled"] },
      ),
    ).toBe("team_id=t1&types=story&types=bug&exclude_states=canceled");
  });
});
