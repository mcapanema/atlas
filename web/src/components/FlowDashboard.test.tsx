import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./EChart", () => ({
  EChart: () => <div data-testid="echart" />,
}));

import { mockMetricsFetch } from "../test/fixtures";
import { FlowDashboard } from "./FlowDashboard";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("FlowDashboard", () => {
  it("renders stat tiles and the three charts for a team scope", async () => {
    mockMetricsFetch();

    renderWithClient(<FlowDashboard scope={{ teamId: "team-1" }} />);

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    expect(screen.getByText("75%")).toBeInTheDocument(); // flow efficiency
    expect(screen.getByText("Cumulative flow (90d)")).toBeInTheDocument();
    expect(screen.getByText("Weekly throughput (90d)")).toBeInTheDocument();
    expect(screen.getByText("WIP over time (90d)")).toBeInTheDocument();
    expect(screen.getAllByTestId("echart")).toHaveLength(3);

    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain("/api/metrics?team_id=team-1");
    expect(urls).toContain("/api/metrics/history?team_id=team-1");
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
});
