import type { UseQueryResult } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import type { ScopeOverview } from "../api/overview";
import { overviewFixture, snapshotsFixture, teamFixture } from "../test/fixtures";
import { buildTeamRows } from "./teamRows";

function query(state: {
  data?: ScopeOverview;
  isPending?: boolean;
  isError?: boolean;
  isFetching?: boolean;
}) {
  return {
    isPending: false,
    isError: false,
    isFetching: false,
    ...state,
  } as UseQueryResult<ScopeOverview>;
}

// A capture 30 days before metricsFixture.window_end, so a baseline exists.
const withBaseline = overviewFixture({
  snapshots: [
    { ...snapshotsFixture[0], captured_on: "2026-06-10", completed: 2 },
    ...snapshotsFixture,
  ],
}) as ScopeOverview;

describe("buildTeamRows", () => {
  it("reads as pending, with no trends, before a team's query exists", () => {
    const [row] = buildTeamRows([teamFixture], [], true);

    expect(row.state).toBe("pending");
    expect([row.throughputDelta, row.leadDelta, row.pulse]).toEqual([null, null, null]);
  });

  it("computes deltas against the ~30-day-old snapshot when enabled", () => {
    const [row] = buildTeamRows([teamFixture], [query({ data: withBaseline })], true);

    expect(row.state).toBe("ready");
    expect(row.metrics).toBe(withBaseline.metrics);
    expect(row.health).toBe(withBaseline.health);
    expect(row.accuracy).toBe(withBaseline.accuracy);
    expect(row.throughputDelta?.baselineDate).toBe("2026-06-10");
    expect(row.pulse?.trend).toBe("worsening");
  });

  it("withholds deltas but keeps the pulse when filters are non-default", () => {
    const [row] = buildTeamRows([teamFixture], [query({ data: withBaseline })], false);

    expect(row.throughputDelta).toBeNull();
    expect(row.leadDelta).toBeNull();
    expect(row.pulse?.trend).toBe("worsening");
  });

  it("reports a failed query as failed, and as pending again while it retries", () => {
    const [failed, retrying] = buildTeamRows(
      [teamFixture, { ...teamFixture, id: "other" }],
      [query({ isError: true }), query({ isError: true, isFetching: true })],
      true,
    );

    expect(failed.state).toBe("failed");
    expect(retrying.state).toBe("pending");
  });
});
