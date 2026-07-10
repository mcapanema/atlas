import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test/fixtures";
import { AdvisorPage } from "./AdvisorPage";

const team = {
  id: "22222222-2222-2222-2222-222222222222",
  organization_id: "33333333-3333-3333-3333-333333333333",
  name: "Platform",
  external_id: null,
  created_at: "2026-07-01T00:00:00Z",
};

const advice = {
  generated_at: "2026-07-10T00:00:00Z",
  summary: "Flow is healthy.",
  recommendations: [
    {
      title: "Lower WIP",
      priority: "high",
      problem: "WIP is 12 while weekly throughput is 3",
      root_cause: "Work is started faster than it finishes",
      action: "Set a WIP limit of 6",
      evidence: ["wip=12", "completed=3"],
    },
  ],
};

function mockFetch({ configured = true } = {}) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([team]));
    if (url.startsWith("/api/recommendations/status")) {
      return Promise.resolve(jsonResponse({ configured }));
    }
    if (url.startsWith("/api/recommendations")) return Promise.resolve(jsonResponse(advice));
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
}

function renderPage(initialEntry = "/advisor") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AdvisorPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AdvisorPage", () => {
  it("warns when the advisor is not configured", async () => {
    mockFetch({ configured: false });

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/Advisor is not configured/)).toBeInTheDocument(),
    );
  });

  it("does not fetch advice until the button is clicked", async () => {
    mockFetch();

    renderPage(`/advisor?team=${team.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.startsWith("/api/recommendations?"))).toBe(false);
  });

  it("renders summary and recommendations after clicking Get advice", async () => {
    mockFetch();

    renderPage(`/advisor?team=${team.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));

    await waitFor(() => expect(screen.getByText("Flow is healthy.")).toBeInTheDocument());
    expect(screen.getByText("Lower WIP")).toBeInTheDocument();
    expect(screen.getByText(/Work is started faster/)).toBeInTheDocument();
    expect(screen.getByText("wip=12")).toBeInTheDocument();
  });
});
