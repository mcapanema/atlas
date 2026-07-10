import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, metricsFixture } from "../test/fixtures";
import { ExecutiveDashboardPage } from "./ExecutiveDashboardPage";

const teams = [
  {
    id: "22222222-2222-2222-2222-222222222222",
    organization_id: "33333333-3333-3333-3333-333333333333",
    name: "Platform",
    external_id: null,
    created_at: "2026-07-01T00:00:00Z",
  },
  {
    id: "55555555-5555-5555-5555-555555555555",
    organization_id: "33333333-3333-3333-3333-333333333333",
    name: "Growth",
    external_id: null,
    created_at: "2026-07-01T00:00:00Z",
  },
];

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ExecutiveDashboardPage", () => {
  it("lists every team with its flow metrics, linking to its dashboard", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse(teams));
      if (url.startsWith("/api/metrics")) return Promise.resolve(jsonResponse(metricsFixture));
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ExecutiveDashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText("Platform")).toBeInTheDocument());
    expect(screen.getByText("Growth")).toBeInTheDocument();
    expect(screen.getAllByText("4")).toHaveLength(2); // completed per team
    expect(screen.getAllByText("75%")).toHaveLength(2); // flow efficiency
    expect(screen.getByText("Platform").closest("a")).toHaveAttribute(
      "href",
      `/teams?team=${teams[0].id}`,
    );

    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain(`/api/metrics?team_id=${teams[0].id}`);
    expect(urls).toContain(`/api/metrics?team_id=${teams[1].id}`);
  });
});
