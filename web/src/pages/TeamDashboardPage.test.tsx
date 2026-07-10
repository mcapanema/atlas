import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/EChart", () => ({
  EChart: () => <div data-testid="echart" />,
}));

import { historyFixture, jsonResponse, metricsFixture } from "../test/fixtures";
import { TeamDashboardPage } from "./TeamDashboardPage";

const team = {
  id: "22222222-2222-2222-2222-222222222222",
  organization_id: "33333333-3333-3333-3333-333333333333",
  name: "Platform",
  external_id: null,
  created_at: "2026-07-01T00:00:00Z",
};

function mockFetch() {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([team]));
    if (url.startsWith("/api/metrics/history")) {
      return Promise.resolve(jsonResponse(historyFixture));
    }
    if (url.startsWith("/api/metrics")) return Promise.resolve(jsonResponse(metricsFixture));
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
}

function renderPage(initialEntry = "/teams") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <TeamDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
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

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    expect(screen.getAllByTestId("echart")).toHaveLength(3);
  });

  it("deep-links a team via the ?team= search param", async () => {
    mockFetch();

    renderPage(`/teams?team=${team.id}`);

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain(`/api/metrics?team_id=${team.id}`);
  });

  it("prompts for a team before fetching metrics", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Select a team to see its dashboard.")).toBeInTheDocument(),
    );
  });
});
