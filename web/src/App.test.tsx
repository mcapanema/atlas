import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders the Atlas sidebar", () => {
    render(
      <QueryClientProvider client={newClient()}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("Atlas")).toBeInTheDocument();
  });

  it("renders the (lazy-loaded) team dashboard route", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/teams"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // The lazy import + FlowDashboard render chain can exceed Testing
    // Library's default 1000ms findByText timeout under load.
    expect(await screen.findByText("Team Dashboard", {}, { timeout: 5000 })).toBeInTheDocument();
  });

  it("renders the (lazy-loaded) project dashboard route", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/projects"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      await screen.findByText("Project Dashboard", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
  });
});
