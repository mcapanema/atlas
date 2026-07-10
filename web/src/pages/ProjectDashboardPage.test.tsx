import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/EChart", () => ({
  EChart: () => <div data-testid="echart" />,
}));

import { historyFixture, jsonResponse, metricsFixture } from "../test/fixtures";
import { ProjectDashboardPage } from "./ProjectDashboardPage";

const project = {
  id: "44444444-4444-4444-4444-444444444444",
  team_id: "22222222-2222-2222-2222-222222222222",
  name: "Apollo",
  external_id: null,
  created_at: "2026-07-01T00:00:00Z",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProjectDashboardPage", () => {
  it("shows the dashboard scoped to the selected project", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/projects")) return Promise.resolve(jsonResponse([project]));
      if (url.startsWith("/api/metrics/history")) {
        return Promise.resolve(jsonResponse(historyFixture));
      }
      if (url.startsWith("/api/metrics")) return Promise.resolve(jsonResponse(metricsFixture));
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/projects"]}>
          <ProjectDashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.mouseDown(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByTitle("Apollo"));

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain(`/api/metrics?project_id=${project.id}`);
  });
});
