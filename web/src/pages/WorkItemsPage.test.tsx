import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkItemsPage } from "./WorkItemsPage";

function renderWithProviders(ui: React.ReactElement, initialEntries = ["/work-items"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const TEAM_ID = "22222222-2222-2222-2222-222222222222";

function mockApi() {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.startsWith("/api/teams")) {
      return Promise.resolve(
        jsonResponse([
          {
            id: TEAM_ID,
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
        items: [
          {
            id: "11111111-1111-1111-1111-111111111111",
            team_id: TEAM_ID,
            project_id: null,
            title: "Fix login flow",
            type: "bug",
            state: "In Progress",
            external_id: null,
            created_at: "2026-07-01T00:00:00Z",
          },
        ],
        total: 1,
      }),
    );
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WorkItemsPage", () => {
  it("renders work items returned by the API", async () => {
    mockApi();

    renderWithProviders(<WorkItemsPage />);

    await waitFor(() => expect(screen.getByText("Fix login flow")).toBeInTheDocument());
    expect(screen.getByText("In Progress")).toBeInTheDocument();
    expect(screen.getByText("Fix login flow").closest("a")).toHaveAttribute(
      "href",
      "/work-items/11111111-1111-1111-1111-111111111111",
    );

    const calls = vi.mocked(globalThis.fetch).mock.calls.map((call) => String(call[0]));
    expect(
      calls.some((url) => url.includes("limit=50") && url.includes("offset=0")),
    ).toBe(true);
  });

  it("reads the team filter and page from the URL", async () => {
    mockApi();

    renderWithProviders(<WorkItemsPage />, [`/work-items?team=${TEAM_ID}&page=2`]);

    await waitFor(() => {
      const calls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
      expect(
        calls.some((url) => url.includes(`team_id=${TEAM_ID}`) && url.includes("offset=50")),
      ).toBe(true);
    });
  });

  it("renders an error alert when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 500 }));

    renderWithProviders(<WorkItemsPage />);

    await waitFor(() => expect(screen.getByText("Failed to load teams")).toBeInTheDocument());
  });
});
