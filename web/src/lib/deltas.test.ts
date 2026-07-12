import { describe, expect, it } from "vitest";

import type { MetricSnapshot } from "../api/snapshots";
import { computeDelta, leadTimePulse, pickBaseline } from "./deltas";

function snapshot(captured_on: string, overrides: Partial<MetricSnapshot> = {}): MetricSnapshot {
  return {
    captured_on,
    window_days: 30,
    completed: 4,
    wip: 2,
    lead_time_p50_seconds: 172800,
    lead_time_p85_seconds: 345600,
    cycle_time_p50_seconds: 86400,
    cycle_time_p85_seconds: 259200,
    blocked_seconds: 0,
    flow_efficiency: 0.75,
    ...overrides,
  };
}

const AS_OF = "2026-07-12T00:00:00Z";

describe("pickBaseline", () => {
  it("picks the capture closest to the target day", () => {
    const snapshots = [
      snapshot("2026-06-10"),
      snapshot("2026-06-13"),
      snapshot("2026-07-11"),
    ];
    expect(pickBaseline(snapshots, AS_OF, 30)?.captured_on).toBe("2026-06-13");
  });

  it("returns null when the nearest capture is outside tolerance", () => {
    expect(pickBaseline([snapshot("2026-07-11")], AS_OF, 30, 7)).toBeNull();
    expect(pickBaseline([], AS_OF, 30)).toBeNull();
  });
});

describe("computeDelta", () => {
  it("reports adverse and favorable moves direction-aware", () => {
    // Lead time up 38% = bad.
    const worse = computeDelta(138, 100, true, "2026-06-12");
    expect(worse).toMatchObject({ direction: "up", good: false, baselineDate: "2026-06-12" });
    expect(worse?.pct).toBeCloseTo(0.38);
    // Throughput up = good.
    expect(computeDelta(9, 6, false, "2026-06-12")).toMatchObject({
      direction: "up",
      good: true,
    });
    // Lead time down = good.
    expect(computeDelta(80, 100, true, "2026-06-12")).toMatchObject({
      direction: "down",
      good: true,
    });
  });

  it("treats sub-0.5% moves as flat", () => {
    expect(computeDelta(1001, 1000, true, "2026-06-12")).toMatchObject({
      direction: "flat",
      good: null,
      pct: 0,
    });
  });

  it("returns null without a usable pair", () => {
    expect(computeDelta(null, 100, true, "2026-06-12")).toBeNull();
    expect(computeDelta(100, null, true, "2026-06-12")).toBeNull();
    expect(computeDelta(100, 0, true, "2026-06-12")).toBeNull();
  });
});

describe("leadTimePulse", () => {
  it("reads a worsening week from rising P85 captures", () => {
    const pulse = leadTimePulse(
      [
        snapshot("2026-07-06", { lead_time_p85_seconds: 300000 }),
        snapshot("2026-07-09", { lead_time_p85_seconds: 340000 }),
        snapshot("2026-07-11", { lead_time_p85_seconds: 400000 }),
        // Outside the 7d window — must be excluded.
        snapshot("2026-06-01", { lead_time_p85_seconds: 1 }),
      ],
      AS_OF,
    );
    expect(pulse?.points).toEqual([300000, 340000, 400000]);
    expect(pulse?.trend).toBe("worsening");
  });

  it("reads improving and steady trends", () => {
    const improving = leadTimePulse(
      [
        snapshot("2026-07-06", { lead_time_p85_seconds: 400000 }),
        snapshot("2026-07-11", { lead_time_p85_seconds: 300000 }),
      ],
      AS_OF,
    );
    expect(improving?.trend).toBe("improving");
    const steady = leadTimePulse(
      [
        snapshot("2026-07-06", { lead_time_p85_seconds: 400000 }),
        snapshot("2026-07-11", { lead_time_p85_seconds: 401000 }),
      ],
      AS_OF,
    );
    expect(steady?.trend).toBe("steady");
  });

  it("reads a zero baseline as worsening only when values appear", () => {
    const pulse = leadTimePulse(
      [
        snapshot("2026-07-06", { lead_time_p85_seconds: 0 }),
        snapshot("2026-07-11", { lead_time_p85_seconds: 100 }),
      ],
      AS_OF,
    );
    expect(pulse?.trend).toBe("worsening");
    const steady = leadTimePulse(
      [
        snapshot("2026-07-06", { lead_time_p85_seconds: 0 }),
        snapshot("2026-07-11", { lead_time_p85_seconds: 0 }),
      ],
      AS_OF,
    );
    expect(steady?.trend).toBe("steady");
  });

  it("returns null with fewer than two usable points", () => {
    expect(leadTimePulse([snapshot("2026-07-11")], AS_OF)).toBeNull();
    expect(
      leadTimePulse(
        [
          snapshot("2026-07-06", { lead_time_p85_seconds: null }),
          snapshot("2026-07-11", { lead_time_p85_seconds: null }),
        ],
        AS_OF,
      ),
    ).toBeNull();
  });
});
