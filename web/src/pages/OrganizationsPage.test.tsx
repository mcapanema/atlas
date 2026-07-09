import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrganizationsPage } from "./OrganizationsPage";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OrganizationsPage", () => {
  it("renders organizations returned by the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify([
          { id: "11111111-1111-1111-1111-111111111111", name: "Acme", created_at: "2026-07-08T00:00:00Z" },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    renderWithClient(<OrganizationsPage />);

    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
  });
});
