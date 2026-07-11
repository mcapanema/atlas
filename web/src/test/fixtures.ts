import { vi } from "vitest";

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
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

export const distributionFixture = {
  window_start: "2026-04-11T00:00:00Z",
  window_end: "2026-07-10T00:00:00Z",
  bins: [
    { start_days: 0, end_days: 1, count: 0 },
    { start_days: 1, end_days: 2, count: 2 },
    { start_days: 2, end_days: 3, count: 1 },
  ],
};

export const forecastFixture = {
  window_start: "2026-04-11T00:00:00Z",
  window_end: "2026-07-10T00:00:00Z",
  remaining: 12,
  completion: {
    trials: 2000,
    p50_date: "2026-07-22T00:00:00Z",
    p75_date: "2026-07-26T00:00:00Z",
    p85_date: "2026-07-29T00:00:00Z",
    p95_date: "2026-08-04T00:00:00Z",
    outcomes: [
      { days: 10, trials: 400 },
      { days: 12, trials: 1200 },
      { days: 19, trials: 400 },
    ],
  },
  confidence: null,
};

export const teamFixture = {
  id: "22222222-2222-2222-2222-222222222222",
  organization_id: "33333333-3333-3333-3333-333333333333",
  name: "Platform",
  external_id: null,
  created_at: "2026-07-01T00:00:00Z",
};

export function mockMetricsFetch(extraRoutes: Record<string, unknown> = {}) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    for (const [prefix, body] of Object.entries(extraRoutes)) {
      if (url.startsWith(prefix)) return Promise.resolve(jsonResponse(body));
    }
    if (url.startsWith("/api/metrics/lead-time-distribution")) {
      return Promise.resolve(jsonResponse(distributionFixture));
    }
    if (url.startsWith("/api/metrics/history")) {
      return Promise.resolve(jsonResponse(historyFixture));
    }
    if (url.startsWith("/api/forecasts")) {
      return Promise.resolve(jsonResponse(forecastFixture));
    }
    if (url.startsWith("/api/metrics")) {
      return Promise.resolve(jsonResponse(metricsFixture));
    }
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
}
