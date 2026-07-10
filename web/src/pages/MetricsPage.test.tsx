import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MetricsPage } from "./MetricsPage";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MetricsPage", () => {
  it("shows a team's flow metrics after selecting the team", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) {
        return Promise.resolve(
          jsonResponse([
            {
              id: "22222222-2222-2222-2222-222222222222",
              organization_id: "33333333-3333-3333-3333-333333333333",
              name: "Platform",
              external_id: null,
              created_at: "2026-07-01T00:00:00Z",
            },
          ]),
        );
      }
      return Promise.resolve(
        jsonResponse({
          window_start: "2026-06-10T00:00:00Z",
          window_end: "2026-07-10T00:00:00Z",
          completed: 4,
          wip: 2,
          lead_time: {
            p50_seconds: 172800,
            p75_seconds: 259200,
            p85_seconds: 345600,
            p95_seconds: 432000,
            mean_seconds: 216000,
          },
          cycle_time: {
            p50_seconds: 86400,
            p75_seconds: 172800,
            p85_seconds: 259200,
            p95_seconds: 345600,
            mean_seconds: 129600,
          },
          blocked_seconds: 0,
          flow_efficiency: 0.75,
        }),
      );
    });

    renderWithClient(<MetricsPage />);

    fireEvent.mouseDown(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByTitle("Platform"));

    await waitFor(() => expect(screen.getByText("Throughput (30d)")).toBeInTheDocument());
    expect(screen.getByText("4")).toBeInTheDocument(); // completed
    expect(screen.getByText("2d")).toBeInTheDocument(); // lead time P50
    expect(screen.getByText("75%")).toBeInTheDocument(); // flow efficiency
  });

  it("prompts for a team before fetching metrics", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));

    renderWithClient(<MetricsPage />);

    await waitFor(() =>
      expect(
        screen.getByText("Select a team to see its flow metrics (last 30 days)."),
      ).toBeInTheDocument(),
    );
  });

  it("shows an error when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 500 }));

    renderWithClient(<MetricsPage />);

    await waitFor(() => expect(screen.getByText("Failed to load teams")).toBeInTheDocument());
  });
});
