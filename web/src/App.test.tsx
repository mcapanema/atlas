import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { authFixture, jsonResponse, requestUrl } from "./test/fixtures";
import { ThemeProvider } from "./theme/ThemeProvider";

vi.mock("./components/EChart", () => ({ EChart: () => null }));

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function mockSession(session: unknown) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
    Promise.resolve(jsonResponse(requestUrl(input) === "/api/auth/session" ? session : [])),
  );
}

beforeEach(() => {
  mockSession(authFixture());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders the Atlas sidebar with grouped navigation", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Atlas")).toBeInTheDocument();
    for (const group of ["Overview", "Delivery", "Intelligence", "Setup"]) {
      expect(screen.getByText(group)).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Advisor" })).toBeInTheDocument();
  });

  it("collapses the sidebar down to the mark", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Collapse navigation" }));
    expect(screen.getByRole("link", { name: "Atlas home" })).toHaveTextContent("A");
    fireEvent.click(screen.getByRole("button", { name: "Expand navigation" }));
    expect(screen.getByRole("link", { name: "Atlas home" })).toHaveTextContent("Atlas");
  });

  it("switches theme mode from the sidebar footer", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <ThemeProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Switch to dark mode" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    window.localStorage.clear();
  });

  it("offers a skip-to-content link as the first tab stop", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    );
    const skip = await screen.findByRole("link", { name: "Skip to content" });
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
    await screen.findByText("Team Dashboard");
    expect(document.title).toBe("Atlas — Teams");
  });

  it("falls back to the bare product title on unknown routes", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/nowhere"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByRole("link", { name: "Atlas home" });
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
    expect(await screen.findByText("Team Dashboard")).toBeInTheDocument();
  });

  it("renders the (lazy-loaded) project dashboard route", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/projects"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Project Dashboard")).toBeInTheDocument();
  });

  it("lists the Meetings entry in the Intelligence group and routes to it", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/meetings"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("link", { name: "Meetings" })).toBeInTheDocument();
    expect(await screen.findByText("Select a team to prepare a meeting.")).toBeInTheDocument();
    expect(document.title).toBe("Atlas — Meetings");
  });

  it("shows the first-run screen, without the sidebar, while no account exists", async () => {
    mockSession({ setup_required: true, user: null });
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/teams"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      await screen.findByRole("heading", { name: "Create the first account" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Atlas home" })).not.toBeInTheDocument();
  });

  it("shows the sign-in screen to a signed-out visitor", async () => {
    mockSession({ setup_required: false, user: null });
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("opens the app once signed in", async () => {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("link", { name: "Atlas home" })).toBeInTheDocument();
  });

  it("says so when the session check fails", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Couldn't reach Atlas")).toBeInTheDocument();
  });
});

describe("App — opening the gate", () => {
  // The session stays signed out: only the mutation's setQueryData can open the app.
  function mockSignedOut(setupRequired: boolean) {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
      if (url === "/api/auth/session") {
        return Promise.resolve(jsonResponse({ setup_required: setupRequired, user: null }));
      }
      if (url === "/api/auth/sign-in" || url === "/api/auth/setup") {
        return Promise.resolve(jsonResponse(authFixture().user));
      }
      return Promise.resolve(jsonResponse([]));
    });
  }

  function renderApp() {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={["/teams"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  function type(label: string, value: string) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }

  it("opens the app on the asked-for page after signing in", async () => {
    mockSignedOut(false);
    renderApp();
    await screen.findByRole("heading", { name: "Sign in" });

    type("Email", "admin@atlas.local");
    type("Password", "correct-horse-battery");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("link", { name: "Atlas home" })).toBeInTheDocument();
    expect(await screen.findByText("Team Dashboard")).toBeInTheDocument();
  });

  it("opens the app after creating the first account", async () => {
    mockSignedOut(true);
    renderApp();
    await screen.findByRole("heading", { name: "Create the first account" });

    type("Email", "admin@atlas.local");
    type("Name", "Admin");
    type("Password", "correct-horse-battery");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("link", { name: "Atlas home" })).toBeInTheDocument();
  });
});
