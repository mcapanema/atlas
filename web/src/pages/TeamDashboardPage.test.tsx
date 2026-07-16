import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/EChart", () => ({
  EChart: () => <div data-testid="echart" />,
}));

import { jsonResponse, mockMetricsFetch, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { TeamDashboardPage } from "./TeamDashboardPage";

function mockFetch() {
  mockMetricsFetch({ "/api/teams": [teamFixture] });
}

function renderPage(initialEntry = "/teams") {
  return renderWithClient(<TeamDashboardPage />, [initialEntry]);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TeamDashboardPage", () => {
  it("shows the dashboard after selecting a team", async () => {
    mockFetch();

    renderPage();

    fireEvent.mouseDown(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByTitle("Platform"));

    // Wait for the full render (all 5 charts): FlowDashboard's loading skeleton gates
    // ForecastCard's mount on metrics/history, so its own forecast fetch starts later
    // and can still be pending when just the stat tiles have appeared.
    await waitFor(() => expect(screen.getAllByTestId("echart")).toHaveLength(5));
    expect(screen.getByText("Throughput (30d)")).toBeInTheDocument();
  });

  it("deep-links a team via the ?team= search param", async () => {
    mockFetch();

    renderPage(`/teams?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain(`/api/metrics?team_id=${teamFixture.id}`);
  });

  it("shows an error when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderPage();

    await waitFor(() => expect(screen.getByText("Failed to load teams")).toBeInTheDocument());
  });

  it("prompts for a team before fetching metrics", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Select a team to see its dashboard.")).toBeInTheDocument(),
    );
  });

  it("threads URL filters into the metrics requests and labels", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(
      <TeamDashboardPage />,
      [`/teams?team=${teamFixture.id}&window=90&types=story,bug&xstates=canceled`],
    );

    await screen.findByText("Throughput (90d)");

    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
    const flowUrl = urls.find((url) => url.startsWith("/api/metrics?"));
    expect(flowUrl).toContain("window_days=90");
    expect(flowUrl).toContain("types=story");
    expect(flowUrl).toContain("types=bug");
    expect(flowUrl).toContain("exclude_states=canceled");
  });

  it("updates the URL when a filter changes", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<TeamDashboardPage />, [`/teams?team=${teamFixture.id}`]);
    await screen.findByText("Throughput (30d)");

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Analysis period" }));
    fireEvent.click(screen.getByText("Last 90 days"));

    await screen.findByText("Throughput (90d)");
  });
});
