import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const captured = vi.hoisted(() => ({ options: [] as unknown[] }));
vi.mock("./EChart", () => ({
  EChart: ({ option }: { option: unknown }) => {
    captured.options.push(option);
    return <div data-testid="echart" />;
  },
}));

import { mockMetricsFetch } from "../test/fixtures";
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

    // Wait for the full render (all 5 charts), not just the stat tiles: FlowDashboard's
    // loading skeleton gates ForecastCard's mount on metrics/history, so ForecastCard's
    // own forecast fetch only starts once they resolve — it lags behind metrics text.
    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(5));
    expect(screen.getByText("Throughput (30d)")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument(); // flow efficiency
    expect(screen.getByText("Cumulative flow (90d)")).toBeInTheDocument();
    expect(screen.getByText("Weekly throughput (90d)")).toBeInTheDocument();
    expect(screen.getByText("WIP over time (90d)")).toBeInTheDocument();
    expect(screen.getByText("Lead time distribution (90d)")).toBeInTheDocument();
    expect(screen.getByText("Completion forecast")).toBeInTheDocument();
    expect(screen.getAllByTestId("echart")).toHaveLength(5);

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

  it("reuses chart option objects across re-renders", async () => {
    mockMetricsFetch();

    const { rerender } = renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);
    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(5));

    const firstRender = [...captured.options];
    captured.options.length = 0;
    rerender(<FlowDashboard scope={{ teamId: "team-1" }} />);

    expect(captured.options).toHaveLength(5);
    captured.options.forEach((option, i) => expect(option).toBe(firstRender[i]));
  });
});
