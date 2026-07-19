import { screen, waitFor, within } from "@testing-library/react";
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
  healthFixture,
  historyFixture,
  jsonResponse,
  metricsFixture,
  mockMetricsFetch,
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
  it("renders stat tiles and the three charts for a team scope", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    // Wait for the full render (all 6 charts), not just the stat tiles: FlowDashboard's
    // loading skeleton gates ForecastCard's mount on metrics/history, so ForecastCard's
    // own forecast fetch only starts once they resolve — it lags behind metrics text.
    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(6));
    expect(screen.getByText("Throughput (30d)")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument(); // flow efficiency
    expect(screen.getByText("Cumulative flow (90d)")).toBeInTheDocument();
    expect(screen.getByText("Weekly throughput (90d)")).toBeInTheDocument();
    expect(screen.getByText("WIP over time (90d)")).toBeInTheDocument();
    expect(screen.getByText("Lead time distribution (90d)")).toBeInTheDocument();
    expect(screen.getByText("Lead time trend")).toBeInTheDocument();
    expect(screen.getByText("Completion forecast")).toBeInTheDocument();
    expect(screen.getAllByTestId("echart")).toHaveLength(6);

    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain("/api/metrics?team_id=team-1");
    expect(urls).toContain("/api/metrics/history?team_id=team-1");
    expect(urls).toContain("/api/metrics/lead-time-distribution?team_id=team-1");
    expect(urls).toContain("/api/forecasts?team_id=team-1");
  });

  it("scopes requests by project", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ projectId: "proj-1" }} />);

    await waitFor(() =>
      expect(
        vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0])),
      ).toContain("/api/metrics?project_id=proj-1"),
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
    captured.options.forEach((option, i) => expect(option).toBe(firstRender[i]));
  });

  it("renders queue and touch time tiles", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Queue time P50")).toBeInTheDocument());
    expect(screen.getByText("Touch time P50")).toBeInTheDocument();
  });

  it("renders the aging WIP table", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Aging WIP")).toBeInTheDocument());
    expect(screen.getByText("Stuck item")).toBeInTheDocument();
    expect(screen.getByText("over P85")).toBeInTheDocument();
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
    expect(
      within(strip).getByText("Last 30 days · 10-06-2026 – 10-07-2026"),
    ).toBeInTheDocument();
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
          { name: "risk", score: 5, reason: "4 of 6 in-progress items blocked or aging past cycle p85" },
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

  it("omits the health strip when the scope has no health data", async () => {
    mockMetricsFetch({
      "/api/metrics/health": { ...healthFixture, score: null, band: null, components: [] },
    });

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    expect(screen.queryByRole("region", { name: "Delivery health" })).toBeNull();
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
    expect(alert).toHaveTextContent(/3 days/i);
  });

  it("says nothing about freshness when the data is current", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(6));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

test("renders lead time trend from snapshots", async () => {
  mockMetricsFetch();
  renderWithClient(<FlowDashboard scope={{ teamId: "t-1" }} />);

  expect(await screen.findByText("Lead time trend")).toBeInTheDocument();
});
