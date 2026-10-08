import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  healthFixture,
  jsonResponse,
  metricsFixture,
  mockMetricsFetch,
  overviewFixture,
  statesFixture,
  teamFixture,
  requestUrl,
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

  it("words the WIP column as of the range end when a custom range is set", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />, ["/?start=2026-06-01&end=2026-06-30"]);
    await screen.findByText("Platform");

    fireEvent.focus(screen.getAllByText("WIP")[0]);
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent(
      "Work items in progress at the end of the selected range: started, and not yet completed, moved back, or canceled by then.",
    );
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
      [`/api/metrics/overview?team_id=${teams[0].id}`]: overviewFixture({
        metrics: platformMetrics,
      }),
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({ metrics: growthMetrics }),
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
    expect(screen.getByText("Last 30 days · 10-06-2026 – 10-07-2026")).toBeInTheDocument();
    // A healthy portfolio is quiet: no risk rows to open…
    expect(screen.queryByRole("button", { name: /risk reasons/i })).not.toBeInTheDocument();
    // …and no blank, unnamed toggle column waiting for one.
    await screen.findByText("Platform");
    expect(screen.getAllByRole("columnheader").filter((th) => th.textContent === "")).toEqual([]);
  });

  it("shows an at-risk team's reasons under its own row, open by default", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({ health: criticalHealth }),
    });
    renderWithClient(<ExecutiveDashboardPage />);

    expect(await screen.findByText("1 of 2 teams at risk")).toBeInTheDocument();
    expect(
      screen.getByText(/Growth: 4 of 6 in-progress items blocked or aging past cycle p85/),
    ).toBeInTheDocument();

    // Health arrives after the row renders — it must still open by default.
    const toggle = await screen.findByRole("button", { name: "Risk reasons for Growth" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const detail = toggle.closest("tr")?.nextElementSibling as HTMLElement;
    // Two weakest component reasons, verbatim…
    expect(
      within(detail).getByText("4 of 6 in-progress items blocked or aging past cycle p85"),
    ).toBeInTheDocument();
    expect(
      within(detail).getByText("completed 1 recently vs 5 in the prior half-window"),
    ).toBeInTheDocument();
    // …not the third-weakest…
    expect(within(detail).queryByText("lead time p95 is 2.9x p50")).not.toBeInTheDocument();
    // …and the 7-day lead-time pulse (snapshotsFixture: 345600 → 432000, +25%).
    expect(within(detail).getByText("lead time P85 worsening this week")).toBeInTheDocument();
    // No separate card stack restating the table.
    expect(screen.queryByLabelText("Teams needing attention")).not.toBeInTheDocument();
  });

  it("lets the EM fold an at-risk team's reasons away", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({ health: criticalHealth }),
    });
    renderWithClient(<ExecutiveDashboardPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Risk reasons for Growth" }));

    const toggle = await screen.findByRole("button", { name: "Risk reasons for Growth" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // rc-table keeps a collapsed row's DOM and hides it with display:none.
    expect(
      screen.getByText("completed 1 recently vs 5 in the prior half-window"),
    ).not.toBeVisible();
  });

  it("gives healthy teams no risk toggle", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({ health: criticalHealth }),
    });
    renderWithClient(<ExecutiveDashboardPage />);

    await screen.findByRole("button", { name: "Risk reasons for Growth" });
    expect(screen.queryByRole("button", { name: /risk reasons for Platform/i })).toBeNull();
  });

  it("gives unscored and failed teams no risk toggle", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse(teams));
      if (url.startsWith("/api/work-items/states")) {
        return Promise.resolve(jsonResponse(statesFixture));
      }
      // Growth's overview fails; Platform answers but health can't score it.
      if (url.includes(teams[1].id)) return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
      return Promise.resolve(
        jsonResponse(
          overviewFixture({
            health: { ...healthFixture, score: null, band: null, components: [] },
          }),
        ),
      );
    });
    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(
      () => expect(screen.getByText("Data failed to load for Growth")).toBeInTheDocument(),
      { timeout: 5000 },
    );
    expect(screen.queryByRole("button", { name: /risk reasons/i })).toBeNull();
  });

  it("opens a team from its row but not from its risk toggle", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({ health: criticalHealth }),
    });
    renderWithClient(
      <Routes>
        <Route path="/" element={<ExecutiveDashboardPage />} />
        <Route path="/teams" element={<p>Team page</p>} />
      </Routes>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Risk reasons for Growth" }));
    expect(screen.queryByText("Team page")).toBeNull();

    // The row itself remains the shortcut to the team.
    const growthRow = screen.getByText("Growth").closest("tr");
    if (!growthRow) throw new Error("Expected Growth row to render");
    fireEvent.click(within(growthRow).getAllByRole("cell")[3]);
    expect(await screen.findByText("Team page")).toBeInTheDocument();
  });

  it("sorts the table worst-health-first by default", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({ health: criticalHealth }),
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

  it("marks Health, not Team, as the sorted column", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({ health: criticalHealth }),
    });
    renderWithClient(<ExecutiveDashboardPage />);
    await screen.findByRole("button", { name: "Risk reasons for Growth" });

    // The expand column must not shift the sort indicator onto its neighbor.
    const header = (label: string) =>
      screen.getAllByRole("columnheader").find((th) => th.textContent === label);
    expect(header("Health")).toHaveAttribute("aria-sort", "ascending");
    expect(header("Team")).not.toHaveAttribute("aria-sort");
  });

  it("annotates throughput and lead time with deltas vs the prior window", async () => {
    mockMetricsFetch({
      "/api/teams": [teamFixture],
      "/api/metrics/overview": overviewFixture({ snapshots: baselineSnapshots }),
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
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse(teams));
      if (url.startsWith("/api/work-items/states")) {
        return Promise.resolve(jsonResponse(statesFixture));
      }
      // The second team's overview fails; the first team stays healthy.
      if (url.includes(teams[1].id)) return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
      return Promise.resolve(jsonResponse(overviewFixture()));
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
    // Health + 5 metrics columns + accuracy, all fed by the failed overview.
    expect(within(growthRow).getAllByText("unavailable")).toHaveLength(7);
    expect(within(growthRow).queryByText("—")).not.toBeInTheDocument();
  });

  it("retries only the teams whose data failed", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse(teams));
      if (url.startsWith("/api/work-items/states")) {
        return Promise.resolve(jsonResponse(statesFixture));
      }
      if (url.includes(teams[1].id)) return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
      return Promise.resolve(jsonResponse(overviewFixture()));
    });
    const overviewCalls = (teamId: string) =>
      vi
        .mocked(fetch)
        .mock.calls.filter((call) =>
          requestUrl(call[0]).startsWith(`/api/metrics/overview?team_id=${teamId}`),
        ).length;

    renderWithClient(<ExecutiveDashboardPage />);
    await waitFor(
      () => expect(screen.getByText("Data failed to load for Growth")).toBeInTheDocument(),
      { timeout: 5000 },
    );
    const platformBefore = overviewCalls(teams[0].id);
    const growthBefore = overviewCalls(teams[1].id);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(overviewCalls(teams[1].id)).toBe(growthBefore + 1));
    expect(overviewCalls(teams[0].id)).toBe(platformBefore);
  });

  it("re-skeletons failed cells while a retry is in flight", async () => {
    let failedOnce = false;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      if (url.startsWith("/api/work-items/states")) {
        return Promise.resolve(jsonResponse(statesFixture));
      }
      if (failedOnce) return new Promise(() => {}); // the retry hangs
      failedOnce = true;
      return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
    });

    renderWithClient(<ExecutiveDashboardPage />);
    await screen.findByText("Data failed to load for Platform");
    expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getAllByLabelText("Loading").length).toBeGreaterThan(0));
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument();
  });

  it("resolves each team's row independently", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse(teams));
      if (url.startsWith("/api/work-items/states")) {
        return Promise.resolve(jsonResponse(statesFixture));
      }
      if (url.includes(teams[1].id)) return new Promise(() => {}); // Growth stays in flight
      return Promise.resolve(jsonResponse(overviewFixture()));
    });

    renderWithClient(<ExecutiveDashboardPage />);

    const platformRow = (await screen.findByText("Platform")).closest("tr");
    const growthRow = screen.getByText("Growth").closest("tr");
    if (!platformRow || !growthRow) throw new Error("Expected team rows to render");
    await waitFor(() => expect(within(platformRow).getByText("75%")).toBeInTheDocument());
    expect(within(growthRow).getAllByLabelText("Loading").length).toBeGreaterThan(0);
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
      "/api/metrics/overview": overviewFixture({
        snapshots: [
          {
            ...baselineSnapshots[0],
            completed: metricsFixture.completed,
            lead_time_p85_seconds: metricsFixture.lead_time.p85_seconds,
          },
        ],
      }),
    });
    renderWithClient(<ExecutiveDashboardPage />);

    const flat = await screen.findByLabelText("throughput unchanged versus prior 30-day window");
    expect(flat.className).toContain("delta--flat");
  });

  it("renders skeletons, not em dashes, while metrics are in flight", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
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
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({ health: criticalHealth }),
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
    // Growth renders once — its table row; no card restates it.
    expect(screen.getAllByText("Growth")).toHaveLength(1);
  });

  it("right-aligns figures so magnitudes compare down a column", async () => {
    mockMetricsFetch({
      "/api/teams": [teamFixture],
      [`/api/metrics/overview?team_id=${teamFixture.id}`]: overviewFixture({
        metrics: { ...metricsFixture, completed: 17 },
      }),
    });
    renderWithClient(<ExecutiveDashboardPage />);

    const figure = await screen.findByText("17");
    expect(figure.closest("td")).toHaveStyle({ textAlign: "right" });
  });

  it("keeps figures aligned when only some teams have a delta", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/overview?team_id=${teams[0].id}`]: overviewFixture({
        metrics: { ...metricsFixture, completed: 17 },
        snapshots: baselineSnapshots,
      }),
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({
        metrics: { ...metricsFixture, completed: 23 },
        snapshots: [],
      }),
    });
    renderWithClient(<ExecutiveDashboardPage />);

    // Both rows reserve the delta slot, so 17 and 23 end on the same edge.
    await waitFor(() =>
      expect(screen.getByText("17").nextElementSibling).toHaveClass("delta-slot"),
    );
    expect(screen.getByText("23").nextElementSibling).toHaveClass("delta-slot");
  });

  it("keeps a missing figure's dash on the figures' edge", async () => {
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics/overview?team_id=${teams[0].id}`]: overviewFixture({
        metrics: { ...metricsFixture, completed: 17 },
        snapshots: baselineSnapshots,
      }),
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({
        metrics: { ...metricsFixture, lead_time: null },
        snapshots: [],
      }),
    });
    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(() =>
      expect(screen.getByText("17").nextElementSibling).toHaveClass("delta-slot"),
    );
    const growthRow = screen.getByText("Growth").closest("tr");
    if (!growthRow) throw new Error("Expected Growth row to render");
    // Growth has no lead time: its "—" reserves the same slot real figures do.
    const slotted = within(growthRow)
      .getAllByText("—")
      .filter((dash) => dash.nextElementSibling?.classList.contains("delta-slot"));
    expect(slotted).toHaveLength(1);
  });

  it("names a lone at-risk team instead of a one-of-one count", async () => {
    mockMetricsFetch({
      "/api/teams": [teamFixture],
      [`/api/metrics/overview?team_id=${teamFixture.id}`]: overviewFixture({
        health: criticalHealth,
      }),
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
      [`/api/metrics/overview?team_id=${teams[1].id}`]: overviewFixture({
        health: { ...healthFixture, score: null, band: null, components: [] },
      }),
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

  it("threads URL filters into per-team overview requests", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />, ["/?window=90&xstates=canceled"]);

    // `findByText(/Last 90 days/)` would also match MetricsFilterBar's period
    // Select label, which renders from the URL alone before any fetch — wait
    // on the as-of line specifically so this only resolves once flow metrics
    // have actually loaded.
    await waitFor(() =>
      expect(document.querySelector(".page-asof")).toHaveTextContent(/Last 90 days/),
    );

    const urls = vi.mocked(fetch).mock.calls.map((call) => requestUrl(call[0]));
    const overviewUrl = urls.find((url) => url.startsWith("/api/metrics/overview?"));
    expect(overviewUrl).toContain("window_days=90");
    expect(overviewUrl).toContain("exclude_states=canceled");
  });

  it("updates the URL and requests when a filter changes", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />);
    await waitFor(() =>
      expect(document.querySelector(".page-asof")).toHaveTextContent(/Last 30 days/),
    );

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Analysis period" }));
    fireEvent.click(screen.getByText("Last 90 days"));

    await waitFor(() =>
      expect(document.querySelector(".page-asof")).toHaveTextContent(/Last 90 days/),
    );
    const urls = vi.mocked(fetch).mock.calls.map((call) => requestUrl(call[0]));
    expect(
      urls.some(
        (url) => url.startsWith("/api/metrics/overview?") && url.includes("window_days=90"),
      ),
    ).toBe(true);
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

  it("asks for each team's row in one request, not four", async () => {
    mockMetricsFetch({ "/api/teams": teams });
    renderWithClient(<ExecutiveDashboardPage />);
    await screen.findByText("All 2 teams healthy");

    const urls = vi.mocked(fetch).mock.calls.map((call) => requestUrl(call[0]));
    for (const team of teams) {
      expect(
        urls.filter((url) => url.startsWith(`/api/metrics/overview?team_id=${team.id}`)),
      ).toHaveLength(1);
    }
    for (const legacy of [
      "/api/metrics?",
      "/api/metrics/health",
      "/api/metrics/snapshots",
      "/api/forecasts/accuracy",
    ]) {
      expect(urls.some((url) => url.startsWith(legacy))).toBe(false);
    }
  });
});
