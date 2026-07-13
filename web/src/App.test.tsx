import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { ThemeProvider } from "./theme/ThemeProvider";

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
  it("renders the Atlas sidebar with grouped navigation", () => {
    render(
      <QueryClientProvider client={newClient()}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("Atlas")).toBeInTheDocument();
    for (const group of ["Overview", "Delivery", "Intelligence", "Setup"]) {
      expect(screen.getByText(group)).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Advisor" })).toBeInTheDocument();
  });

  it("collapses the sidebar down to the mark", () => {
    render(
      <QueryClientProvider client={newClient()}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Collapse navigation" }));
    expect(screen.getByRole("link", { name: "Atlas home" })).toHaveTextContent("A");
    fireEvent.click(screen.getByRole("button", { name: "Expand navigation" }));
    expect(screen.getByRole("link", { name: "Atlas home" })).toHaveTextContent("Atlas");
  });

  it("switches theme mode from the sidebar footer", () => {
    render(
      <QueryClientProvider client={newClient()}>
        <ThemeProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    window.localStorage.clear();
  });

  it("offers a skip-to-content link as the first tab stop", () => {
    render(
      <QueryClientProvider client={newClient()}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    );
    const skip = screen.getByRole("link", { name: "Skip to content" });
    expect(skip).toHaveAttribute("href", "#main");
    expect(document.querySelector("main#main")).not.toBeNull();
  });

  it("titles the document per route", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/teams"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText("Team Dashboard", {}, { timeout: 5000 });
    expect(document.title).toBe("Atlas — Teams");
  });

  it("falls back to the bare product title on unknown routes", () => {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/nowhere"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(document.title).toBe("Atlas");
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

  it("lists the Meetings entry in the Intelligence group and routes to it", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/meetings"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("link", { name: "Meetings" })).toBeInTheDocument();
    expect(await screen.findByText("Select a team to prepare a meeting.")).toBeInTheDocument();
    expect(document.title).toBe("Atlas — Meetings");
  });
});
