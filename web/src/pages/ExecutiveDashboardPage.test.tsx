import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  healthFixture,
  jsonResponse,
  metricsFixture,
  mockMetricsFetch,
  teamFixture,
} from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { ExecutiveDashboardPage } from "./ExecutiveDashboardPage";

const teams = [
  teamFixture,
  { ...teamFixture, id: "55555555-5555-5555-5555-555555555555", name: "Growth" },
];

const criticalHealth = {
  ...healthFixture,
  score: 24,
  band: "critical",
  components: [
    { name: "risk", score: 5, reason: "4 of 6 in-progress items blocked or aging past cycle p85" },
    { name: "flow", score: 30, reason: "completed 1 recently vs 5 in the prior half-window" },
    { name: "predictability", score: 60, reason: "lead time p95 is 2.9x p50" },
  ],
};

// Baseline exactly 30d before metricsFixture.window_end (2026-07-10):
// completed 2 (current 4 → up 100%, good), lead P85 172800 (current 345600
// → up 100%, bad).
const baselineSnapshots = [
  {
    captured_on: "2026-06-10",
    window_days: 30,
    completed: 2,
    wip: 1,
    lead_time_p50_seconds: 86400,
    lead_time_p85_seconds: 172800,
    cycle_time_p50_seconds: 43200,
    cycle_time_p85_seconds: 129600,
    blocked_seconds: 0,
    flow_efficiency: 0.8,
  },
];

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ExecutiveDashboardPage", () => {
  it("opens column definitions on keyboard focus, not just hover", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />);
    await screen.findByText("Platform");

    fireEvent.focus(screen.getAllByText("WIP")[0]);
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Work items in progress right now.");
  });

  it("names the table for assistive tech", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />);

    expect(
      await screen.findByRole("table", { name: "Delivery metrics by team" }),
    ).toBeInTheDocument();
  });

  it("lists every team with its flow metrics, linking to its dashboard", async () => {
    const platformMetrics = { ...metricsFixture, completed: 4 };
    const growthMetrics = { ...metricsFixture, completed: 9 };
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics?team_id=${teams[0].id}`]: platformMetrics,
      [`/api/metrics?team_id=${teams[1].id}`]: growthMetrics,
    });

    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(() => expect(screen.getByText("Platform")).toBeInTheDocument());
    expect(screen.getByText("Growth")).toBeInTheDocument();

    const platformRow = screen.getByText("Platform").closest("tr");
    const growthRow = screen.getByText("Growth").closest("tr");
    if (!platformRow || !growthRow) throw new Error("Expected team rows to render");
    await waitFor(() => expect(within(platformRow).getByText("4")).toBeInTheDocument());
    expect(within(growthRow).getByText("9")).toBeInTheDocument();
    expect(within(platformRow).getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("Platform").closest("a")).toHaveAttribute(
      "href",
      `/teams?team=${teams[0].id}`,
    );
  });

  it("leads with an all-healthy headline and the metrics window", async () => {
    mockMetricsFetch({ "/api/teams": teams });
    renderWithClient(<ExecutiveDashboardPage />);

    expect(await screen.findByText("All 2 teams healthy")).toBeInTheDocument();
    expect(screen.getByText("Last 30 days · Jun 10 – Jul 10")).toBeInTheDocument();
    // Healthy portfolio renders no attention section.
    expect(screen.queryByLabelText("Teams needing attention")).not.toBeInTheDocument();
  });

  it("headlines the worst team and raises an attention card when a team is at risk", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/health?team_id=${teams[1].id}`]: criticalHealth,
    });
    renderWithClient(<ExecutiveDashboardPage />);

    expect(await screen.findByText("1 of 2 teams at risk")).toBeInTheDocument();
    expect(
      screen.getByText(/Growth: 4 of 6 in-progress items blocked or aging past cycle p85/),
    ).toBeInTheDocument();

    const attention = await screen.findByLabelText("Teams needing attention");
    // Two weakest component reasons, verbatim.
    expect(
      within(attention).getByText("4 of 6 in-progress items blocked or aging past cycle p85"),
    ).toBeInTheDocument();
    expect(
      within(attention).getByText("completed 1 recently vs 5 in the prior half-window"),
    ).toBeInTheDocument();
    // ...but not the third-weakest.
    expect(within(attention).queryByText("lead time p95 is 2.9x p50")).not.toBeInTheDocument();
  });

  it("sorts the table worst-health-first by default", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/health?team_id=${teams[1].id}`]: criticalHealth,
    });
    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(() => {
      const rows = screen
        .getAllByRole("row")
        .map((row) => row.textContent ?? "")
        .filter((text) => text.includes("Platform") || text.includes("Growth"));
      expect(rows[0]).toContain("Growth"); // score 24 before score 82
    });
  });

  it("annotates throughput and lead time with deltas vs the prior window", async () => {
    mockMetricsFetch({
      "/api/teams": [teamFixture],
      "/api/metrics/snapshots": baselineSnapshots,
    });
    renderWithClient(<ExecutiveDashboardPage />);

    const throughputDelta = await screen.findByLabelText(
      "throughput up 100% versus prior 30-day window",
    );
    expect(throughputDelta.className).toContain("delta--good");
    const leadDelta = screen.getByLabelText("lead time up 100% versus prior 30-day window");
    expect(leadDelta.className).toContain("delta--bad");
  });

  it("omits deltas when snapshot history has no usable baseline", async () => {
    // Default snapshotsFixture captures are 07-09/07-10 — 29 days off target.
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />);

    await screen.findByText("Platform is healthy");
    expect(screen.queryByText(/versus prior 30-day window/)).not.toBeInTheDocument();
  });

  it("names the teams whose data failed and offers a retry", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse(teams));
      // Every query for the second team fails; the first team stays healthy.
      if (url.includes(teams[1].id)) return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
      if (url.startsWith("/api/metrics/snapshots")) return Promise.resolve(jsonResponse([]));
      if (url.startsWith("/api/metrics/health")) return Promise.resolve(jsonResponse(healthFixture));
      if (url.startsWith("/api/forecasts/accuracy")) {
        return Promise.resolve(jsonResponse({ evaluated: 0, pending: 0, p50_hit_rate: null, p85_hit_rate: null, mean_abs_error_days: null }));
      }
      return Promise.resolve(jsonResponse(metricsFixture));
    });

    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(
      () => expect(screen.getByText("Data failed to load for Growth")).toBeInTheDocument(),
      { timeout: 5000 },
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();

    // Failed cells say so — never the "—" that means "no data".
    const growthRow = screen.getByText("Growth").closest("tr");
    if (!growthRow) throw new Error("Expected Growth row to render");
    // Health + 5 metrics columns + accuracy, all fed by failed queries.
    expect(within(growthRow).getAllByText("unavailable")).toHaveLength(7);
    expect(within(growthRow).queryByText("—")).not.toBeInTheDocument();
  });

  it("re-skeletons failed cells while a retry is in flight", async () => {
    let failedOnce = false;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      if (url.startsWith("/api/metrics/snapshots")) return Promise.resolve(jsonResponse([]));
      if (failedOnce) return new Promise(() => {}); // the retry hangs
      if (url.startsWith("/api/metrics?")) {
        failedOnce = true;
        return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
      }
      if (url.startsWith("/api/metrics/health")) return Promise.resolve(jsonResponse(healthFixture));
      return Promise.resolve(jsonResponse({ evaluated: 0, pending: 0, p50_hit_rate: null, p85_hit_rate: null, mean_abs_error_days: null }));
    });

    renderWithClient(<ExecutiveDashboardPage />);
    await screen.findByText("Data failed to load for Platform");
    expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getAllByLabelText("Loading").length).toBeGreaterThan(0));
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument();
  });

  it("shows resolved figures instead of skeletons while other queries still load", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      if (url.startsWith("/api/metrics?")) return Promise.resolve(jsonResponse(metricsFixture));
      if (url.startsWith("/api/metrics/snapshots")) return Promise.resolve(jsonResponse([]));
      return new Promise(() => {}); // health + accuracy stay pending
    });

    renderWithClient(<ExecutiveDashboardPage />);

    // Metrics cells resolve (flow efficiency 75%) while health/accuracy skeleton.
    expect(await screen.findByText("75%")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Loading").length).toBeGreaterThan(0);
  });

  it("shows a retryable error when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(() => expect(screen.getByText("Couldn't load teams")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("teaches the first-run empty state instead of an empty table", async () => {
    mockMetricsFetch({ "/api/teams": [] });
    renderWithClient(<ExecutiveDashboardPage />);

    expect(
      await screen.findByText("No teams yet — connect Linear to start observing delivery."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Connectors" })).toBeInTheDocument();
  });

  it("marks unchanged metrics as flat instead of inventing movement", async () => {
    mockMetricsFetch({
      "/api/teams": [teamFixture],
      "/api/metrics/snapshots": [
        {
          ...baselineSnapshots[0],
          completed: metricsFixture.completed,
          lead_time_p85_seconds: metricsFixture.lead_time.p85_seconds,
        },
      ],
    });
    renderWithClient(<ExecutiveDashboardPage />);

    const flat = await screen.findByLabelText(
      "throughput unchanged versus prior 30-day window",
    );
    expect(flat.className).toContain("delta--flat");
  });

  it("renders skeletons, not em dashes, while metrics are in flight", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      return new Promise(() => {}); // every metric query stays pending
    });
    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(() => expect(screen.getAllByLabelText("Loading").length).toBeGreaterThan(4));
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  it("sorts by any column on header click", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/health?team_id=${teams[1].id}`]: criticalHealth,
    });
    renderWithClient(<ExecutiveDashboardPage />);
    await screen.findByText("1 of 2 teams at risk");

    for (const label of [
      "Team",
      "Throughput",
      "WIP",
      "Lead time P85",
      "Flow efficiency",
      "Blocked time",
      "Forecast accuracy (P85)",
    ]) {
      // scroll={{x}} renders a hidden measurement header; click the real one.
      fireEvent.click(screen.getAllByText(label)[0]);
    }
    // After sorting by team name ascending then others, the table still lists both teams.
    expect(screen.getByText("Platform")).toBeInTheDocument();
    // Growth renders twice: attention card + table row.
    expect(screen.getAllByText("Growth").length).toBeGreaterThanOrEqual(2);
  });

  it("names a lone at-risk team instead of a one-of-one count", async () => {
    mockMetricsFetch({
      "/api/teams": [teamFixture],
      [`/api/metrics/health?team_id=${teamFixture.id}`]: criticalHealth,
    });
    renderWithClient(<ExecutiveDashboardPage />);

    expect(await screen.findByText("Platform is at risk")).toBeInTheDocument();
    // The reason follows directly — no redundant "Platform:" prefix.
    expect(
      screen.getByText(/— 4 of 6 in-progress items blocked or aging past cycle p85/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Platform: 4 of 6/)).not.toBeInTheDocument();
  });

  it("counts teams health could not score instead of hiding them", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/health?team_id=${teams[1].id}`]: {
        ...healthFixture,
        score: null,
        band: null,
        components: [],
      },
    });
    renderWithClient(<ExecutiveDashboardPage />);

    expect(await screen.findByText("Platform is healthy")).toBeInTheDocument();
    expect(screen.getByText(/1 not scored yet/)).toBeInTheDocument();
  });

  it("shows per-team forecast accuracy and delivery health", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />);

    expect(await screen.findByText("90%")).toBeInTheDocument();
    const badge = await screen.findByRole("button", {
      name: "Health 82 of 100 — healthy. Show component reasons",
    });
    expect(badge).toHaveTextContent("82");
  });

  it("threads URL filters into per-team metrics requests", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />, ["/?window=90&xstates=canceled"]);

    // `findByText(/Last 90 days/)` would also match MetricsFilterBar's period
    // Select label, which renders from the URL alone before any fetch — wait
    // on the as-of line specifically so this only resolves once flow metrics
    // have actually loaded.
    await waitFor(() =>
      expect(document.querySelector(".page-asof")).toHaveTextContent(/Last 90 days/),
    );

    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
    const flowUrl = urls.find((url) => url.startsWith("/api/metrics?"));
    expect(flowUrl).toContain("window_days=90");
    expect(flowUrl).toContain("exclude_states=canceled");
  });

  it("hides delta chips when filters are not the snapshot baseline", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />, ["/?window=90"]);

    // `findByText(/Last 90 days/)` would also match MetricsFilterBar's period
    // Select label, which renders from the URL alone before any fetch — wait
    // on the as-of line specifically so this only resolves once flow metrics
    // have actually loaded.
    await waitFor(() =>
      expect(document.querySelector(".page-asof")).toHaveTextContent(/Last 90 days/),
    );

    // metricsFixture.completed is 4 with a snapshot baseline of 3 — the default
    // view renders a delta chip; a 90d view must not (snapshots are 30d).
    expect(document.querySelector(".delta")).toBeNull();
  });
});
