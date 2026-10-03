import type { UseQueryResult } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { metricsFixture, snapshotsFixture, teamFixture } from "../test/fixtures";
import { buildTeamRows, type TeamQueries } from "./teamRows";

function query<T>(state: {
  data?: T;
  isPending?: boolean;
  isError?: boolean;
  isFetching?: boolean;
}) {
  return {
    isPending: false,
    isError: false,
    isFetching: false,
    ...state,
  } as UseQueryResult<T>;
}

const NO_QUERIES: TeamQueries = { metrics: [], accuracy: [], health: [], snapshots: [] };

// A capture 30 days before metricsFixture.window_end, so a baseline exists.
const withBaseline = [
  { ...snapshotsFixture[0], captured_on: "2026-06-10", completed: 2 },
  ...snapshotsFixture,
];

describe("buildTeamRows", () => {
  it("reads as pending, with no trends, before a team's queries exist", () => {
    const [row] = buildTeamRows([teamFixture], NO_QUERIES, true);

    expect(row.metricsState).toBe("pending");
    expect(row.accuracyState).toBe("pending");
    expect(row.healthState).toBe("pending");
    expect([row.throughputDelta, row.leadDelta, row.pulse]).toEqual([null, null, null]);
  });

  it("computes deltas against the ~30-day-old snapshot when enabled", () => {
    const queries = {
      ...NO_QUERIES,
      metrics: [query({ data: metricsFixture })],
      snapshots: [query({ data: withBaseline })],
    };

    const [row] = buildTeamRows([teamFixture], queries, true);

    expect(row.metricsState).toBe("ready");
    expect(row.throughputDelta?.baselineDate).toBe("2026-06-10");
    expect(row.pulse?.trend).toBe("worsening");
  });

  it("withholds deltas but keeps the pulse when filters are non-default", () => {
    const queries = {
      ...NO_QUERIES,
      metrics: [query({ data: metricsFixture })],
      snapshots: [query({ data: withBaseline })],
    };

    const [row] = buildTeamRows([teamFixture], queries, false);

    expect(row.throughputDelta).toBeNull();
    expect(row.leadDelta).toBeNull();
    expect(row.pulse?.trend).toBe("worsening");
  });

  it("reports a failed query as failed, and as pending again while it retries", () => {
    const failed = query<never>({ isError: true });
    const retrying = query<never>({ isError: true, isFetching: true });

    const [row] = buildTeamRows(
      [teamFixture],
      { ...NO_QUERIES, metrics: [failed], health: [retrying] },
      true,
    );

    expect(row.metricsState).toBe("failed");
    expect(row.healthState).toBe("pending");
  });
});
