import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkItemsPage } from "./WorkItemsPage";

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
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

describe("WorkItemsPage", () => {
  it("renders work items returned by the API", async () => {
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
          items: [
            {
              id: "11111111-1111-1111-1111-111111111111",
              team_id: "22222222-2222-2222-2222-222222222222",
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

  it("renders an error alert when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 500 }));

    renderWithProviders(<WorkItemsPage />);

    await waitFor(() => expect(screen.getByText("Failed to load teams")).toBeInTheDocument());
  });
});
