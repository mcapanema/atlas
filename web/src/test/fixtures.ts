import { vi } from "vitest";

export function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

export const metricsFixture = {
  window_start: "2026-06-10T00:00:00Z",
  window_end: "2026-07-10T00:00:00Z",
  completed: 4,
  wip: 2,
  lead_time: {
    p50_seconds: 172800,
    p75_seconds: 259200,
    p85_seconds: 345600,
    p95_seconds: 432000,
    mean_seconds: 216000,
  },
  cycle_time: {
    p50_seconds: 86400,
    p75_seconds: 172800,
    p85_seconds: 259200,
    p95_seconds: 345600,
    mean_seconds: 129600,
  },
  blocked_seconds: 0,
  flow_efficiency: 0.75,
};

export const historyFixture = {
  window_start: "2026-04-11T00:00:00Z",
  window_end: "2026-07-10T00:00:00Z",
  days: [
    { day: "2026-07-09", todo: 2, in_progress: 2, done: 3 },
    { day: "2026-07-10", todo: 1, in_progress: 2, done: 4 },
  ],
  weeks: [{ start: "2026-07-03T00:00:00Z", end: "2026-07-10T00:00:00Z", completed: 4 }],
};

export function mockMetricsFetch() {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.startsWith("/api/metrics/history")) {
      return Promise.resolve(jsonResponse(historyFixture));
    }
    if (url.startsWith("/api/metrics")) {
      return Promise.resolve(jsonResponse(metricsFixture));
    }
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
}
