import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, test, vi } from "vitest";

const captured = vi.hoisted(() => ({ options: [] as unknown[] }));
vi.mock("./EChart", () => ({
  EChart: ({ option }: { option: unknown }) => {
    captured.options.push(option);
    return <div data-testid="echart" />;
  },
}));

import {
  agingWipFixture,
  distributionFixture,
  healthFixture,
  historyFixture,
  jsonResponse,
  metricsFixture,
  mockMetricsFetch,
  requestUrl,
  snapshotsFixture,
} from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { FlowDashboard } from "./FlowDashboard";

beforeEach(() => {
  captured.options.length = 0;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("FlowDashboard", () => {
  it("labels WIP as of the range end when a custom range is set", async () => {
    mockMetricsFetch();

    renderWithClient(
      <FlowDashboard
        scope={{ teamId: "team-1" }}
        filters={{ start: "2026-09-01", end: "2026-09-14" }}
      />,
    );

    expect(await screen.findByText("WIP (at range end)")).toBeInTheDocument();
    expect(screen.queryByText("WIP (now)")).not.toBeInTheDocument();
    fireEvent.focus(screen.getByText("WIP (at range end)"));
    expect(
      await screen.findByText(/in progress at the end of the selected range/),
    ).toBeInTheDocument();
  });

  it("renders stat tiles and the three charts for a team scope", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    // Wait for the full render (all 6 charts), not just the stat tiles: FlowDashboard's
    // loading skeleton gates ForecastCard's mount on metrics/history, so ForecastCard's
    // own forecast fetch only starts once they resolve — it lags behind metrics text.
    // That multi-hop chain can exceed the default 1000ms waitFor timeout under CI load
    // (same class of flake as App.test.tsx's lazy-route findByText).
    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(6), {
      timeout: 5000,
    });
    expect(screen.getByText("Throughput (30d)")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument(); // flow efficiency
    expect(screen.getByText("Cumulative flow (90d)")).toBeInTheDocument();
    expect(screen.getByText("Weekly throughput (90d)")).toBeInTheDocument();
    expect(screen.getByText("WIP over time (90d)")).toBeInTheDocument();
    expect(screen.getByText("Lead time distribution (90d)")).toBeInTheDocument();
    expect(screen.getByText("Lead time trend")).toBeInTheDocument();
    expect(screen.getByText("Completion forecast")).toBeInTheDocument();
    expect(screen.getAllByTestId("echart")).toHaveLength(6);

    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => requestUrl(c[0]));
    expect(urls).toContain("/api/metrics?team_id=team-1");
    expect(urls).toContain("/api/metrics/history?team_id=team-1");
    expect(urls).toContain("/api/metrics/lead-time-distribution?team_id=team-1");
    expect(urls).toContain("/api/forecasts?team_id=team-1");
  });

  it("scopes requests by project", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ projectId: "proj-1" }} />);

    await waitFor(() =>
      expect(vi.mocked(globalThis.fetch).mock.calls.map((c) => requestUrl(c[0]))).toContain(
        "/api/metrics?project_id=proj-1",
      ),
    );
  });

  it("shows a skeleton while metrics load", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {}));

    const { container } = renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    expect(container.querySelector(".ant-skeleton")).not.toBeNull();
  });

  it("shows an error when metrics fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Failed to load metrics")).toBeInTheDocument());
  });

  it("shows placeholders when lead/cycle time and flow efficiency have no data yet", async () => {
    mockMetricsFetch({
      "/api/metrics?team_id=team-1": {
        ...metricsFixture,
        lead_time: null,
        cycle_time: null,
        flow_efficiency: null,
      },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("reuses chart option objects across re-renders", async () => {
    mockMetricsFetch();

    const { rerender } = renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);
    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(6));

    const firstRender = [...captured.options];
    captured.options.length = 0;
    rerender(<FlowDashboard scope={{ teamId: "team-1" }} />);

    expect(captured.options).toHaveLength(6);
    // By identity, not position: firstRender accumulates every render while
    // the queries settle, so its order is load order, not page order.
    captured.options.forEach((option) => expect(firstRender).toContain(option));
  });

  it("renders queue and touch time tiles", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Queue time P50")).toBeInTheDocument());
    expect(screen.getByText("Touch time P50")).toBeInTheDocument();
  });

  it("pairs each P50 tile with its P85 in a column-first stat grid", async () => {
    mockMetricsFetch();

    const { container } = renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await screen.findByText("Throughput (30d)");
    const grid = container.querySelector(".stat-grid--paired");
    expect(grid).not.toBeNull();
    // DOM order is the pairs: the wide grid flows column-first (P50 above
    // P85), the narrow 2-column grid flows row-first (P50 beside P85).
    const labels = [...grid!.querySelectorAll(".stat__label")].map((el) => el.textContent);
    expect(labels).toEqual([
      "Throughput (30d)",
      "WIP (now)",
      "Lead time P50",
      "Lead time P85",
      "Cycle time P50",
      "Cycle time P85",
      "Queue time P50",
      "Touch time P50",
      "Blocked time (30d)",
      "Flow efficiency",
    ]);
  });

  it("renders the aging WIP table", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Aging WIP")).toBeInTheDocument());
    expect(screen.getByText("Stuck item")).toBeInTheDocument();
    expect(screen.getByText("over P85")).toBeInTheDocument();
  });

  it("puts aging WIP, then the forecast, before the diagnostic charts", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    const forecast = await screen.findByText("Completion forecast", {}, { timeout: 5000 });
    const aging = screen.getByText("Aging WIP");
    const cfd = screen.getByText("Cumulative flow (90d)");
    const follows = (a: Node, b: Node) =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(aging, forecast)).toBe(true);
    expect(follows(forecast, cfd)).toBe(true);
  });

  it("says so instead of drawing empty axes when nothing completed in the window", async () => {
    mockMetricsFetch({
      "/api/metrics/lead-time-distribution": {
        // What the API sends when nothing completed: no bins, no percentiles.
        ...distributionFixture,
        bins: [],
        p50_seconds: null,
        p85_seconds: null,
      },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    expect(await screen.findByText("No items completed in this window.")).toBeInTheDocument();
    expect(screen.getByText("Lead time distribution (90d)")).toBeInTheDocument();
    // CFD, throughput, WIP, trend, forecast — no distribution chart.
    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(5), {
      timeout: 5000,
    });
  });

  it("waits for two snapshots with a lead time before drawing the trend", async () => {
    mockMetricsFetch({
      "/api/metrics/snapshots": [
        { ...snapshotsFixture[0], lead_time_p50_seconds: null, lead_time_p85_seconds: null },
        snapshotsFixture[1],
      ],
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    expect(await screen.findByText(/trend starts once two daily snapshots/i)).toBeInTheDocument();
    expect(screen.getByText("Lead time trend")).toBeInTheDocument();
  });

  it("omits the aging WIP card when nothing is in progress", async () => {
    mockMetricsFetch({ "/api/metrics/aging-wip": { ...agingWipFixture, items: [] } });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    expect(screen.queryByText("Aging WIP")).toBeNull();
  });

  it("leads with a quiet health strip and the metrics window when healthy", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    const strip = await screen.findByRole("region", { name: "Delivery health" });
    expect(
      within(strip).getByRole("button", {
        name: "Health 82 of 100 — healthy. Show component reasons",
      }),
    ).toBeInTheDocument();
    expect(within(strip).getByText("Last 30 days · 10-06-2026 – 10-07-2026")).toBeInTheDocument();
    // Healthy stays quiet — reasons live in the badge popover, not inline.
    expect(screen.queryByText(/lead time p95 is 1.8x p50/)).toBeNull();
  });

  it("raises an attention card with the two weakest reasons when at risk", async () => {
    mockMetricsFetch({
      "/api/metrics/health": {
        ...healthFixture,
        score: 24,
        band: "critical",
        components: [
          {
            name: "risk",
            score: 5,
            reason: "4 of 6 in-progress items blocked or aging past cycle p85",
          },
          { name: "flow", score: 30, reason: "completed 1 recently vs 5 in the prior half-window" },
          { name: "predictability", score: 60, reason: "lead time p95 is 2.9x p50" },
        ],
      },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    expect(
      await screen.findByText("4 of 6 in-progress items blocked or aging past cycle p85"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("completed 1 recently vs 5 in the prior half-window"),
    ).toBeInTheDocument();
    // ...but not the third-weakest.
    expect(screen.queryByText("lead time p95 is 2.9x p50")).toBeNull();
  });

  it("says health isn't scored yet when too few items back it", async () => {
    // Since health_min_sample, a small or idle team is unscored: the strip
    // says so (the Executive page's words) instead of silently vanishing.
    mockMetricsFetch({
      "/api/metrics/health": { ...healthFixture, score: null, band: null, components: [] },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    const strip = await screen.findByRole("region", { name: "Delivery health" });
    expect(strip).toHaveTextContent(/Health not scored yet/);
    expect(strip).toHaveTextContent(/too few items/);
    expect(strip.querySelector(".health-badge")).toBeNull();
  });

  it("warns when the data is older than the window it is charting", async () => {
    // extraRoutes keys are URL prefixes and values are raw bodies —
    // mockMetricsFetch wraps them in jsonResponse itself, so don't pre-wrap.
    mockMetricsFetch({
      "/api/metrics/history": {
        ...historyFixture,
        data_as_of: "2026-07-07T00:00:00Z", // 72h before window_end
      },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/last synced/i);
    expect(alert).toHaveTextContent("07-07-2026");
    expect(alert).toHaveTextContent(/the last 3 days of this window are not ingested yet/i);
    // One line: the explanation is the title itself, not a second paragraph.
    expect(alert.querySelector(".ant-alert-description")).toBeNull();
  });

  it("uses the singular when the data is only one day stale", async () => {
    mockMetricsFetch({
      "/api/metrics/history": {
        ...historyFixture,
        data_as_of: "2026-07-08T18:00:00Z", // 30h before window_end
      },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/the last day of this window is not ingested yet/i);
    expect(alert).not.toHaveTextContent(/1 day/);
  });

  it("tolerates exactly the staleness threshold without warning", async () => {
    mockMetricsFetch({
      "/api/metrics/history": {
        ...historyFixture,
        data_as_of: "2026-07-09T00:00:00Z", // exactly 24h before window_end
      },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(6));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("warns one hour past the staleness threshold", async () => {
    mockMetricsFetch({
      "/api/metrics/history": {
        ...historyFixture,
        data_as_of: "2026-07-08T23:00:00Z", // 25h before window_end
      },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/last synced/i);
  });

  it("says nothing about freshness when the data is current", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(6));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("titles the throughput chart Daily when the buckets are one day each", async () => {
    mockMetricsFetch({
      "/api/metrics/history": {
        ...historyFixture,
        bucket_days: 1,
        buckets: [
          { start: "2026-07-08T00:00:00Z", end: "2026-07-09T00:00:00Z", completed: 1 },
          { start: "2026-07-09T00:00:00Z", end: "2026-07-10T00:00:00Z", completed: 2 },
        ],
      },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} filters={{ windowDays: 7 }} />);

    expect(await screen.findByText("Daily throughput (7d)")).toBeInTheDocument();
    expect(screen.queryByText(/Weekly throughput/)).not.toBeInTheDocument();
  });

  it("still hides the chart when the window holds a single bucket", async () => {
    mockMetricsFetch({
      "/api/metrics/history": {
        ...historyFixture,
        buckets: [{ start: "2026-07-03T00:00:00Z", end: "2026-07-10T00:00:00Z", completed: 41 }],
      },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(5));
    // Not /throughput/i — that also matches the ever-present "Throughput (30d)"
    // stat tile. Scope to the chart card's title pattern instead.
    expect(screen.queryByText(/(Daily|Weekly) throughput/)).not.toBeInTheDocument();
    expect(screen.getByText("Cumulative flow (90d)")).toBeInTheDocument();
  });

  it("defines what each stat measures", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    const trigger = await screen.findByText("Flow efficiency");
    expect(trigger).toHaveAttribute("tabindex", "0");

    fireEvent.focus(trigger);
    expect(await screen.findByText(/Touch time divided by lead time/)).toBeInTheDocument();
  });

  it("labels aging flags with the team's aging percentile", async () => {
    mockMetricsFetch({ "/api/metrics/aging-wip": { ...agingWipFixture, percentile: 70 } });

    renderWithClient(<FlowDashboard scope={{ teamId: "t1" }} />);

    expect(await screen.findByText("over P70")).toBeInTheDocument();
  });

  it("explains how the throughput chart is built", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    const trigger = await screen.findByText("Weekly throughput (90d)");
    fireEvent.focus(trigger);
    expect(
      await screen.findByText(/Work items completed in each trailing 7-day bucket/),
    ).toBeInTheDocument();
  });
});

test("renders lead time trend from snapshots", async () => {
  mockMetricsFetch();
  renderWithClient(<FlowDashboard scope={{ teamId: "t-1" }} />);

  expect(await screen.findByText("Lead time trend")).toBeInTheDocument();
});
