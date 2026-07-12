import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { AdvisorPage } from "./AdvisorPage";

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
    if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
    if (url.startsWith("/api/recommendations/status")) {
      return Promise.resolve(jsonResponse({ configured }));
    }
    if (url.startsWith("/api/recommendations")) return Promise.resolve(jsonResponse(advice));
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
}

function renderPage(initialEntry = "/advisor") {
  return renderWithClient(<AdvisorPage />, [initialEntry]);
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

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.startsWith("/api/recommendations?"))).toBe(false);
  });

  it("renders summary and recommendations after clicking Get advice", async () => {
    mockFetch();

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));

    await waitFor(() => expect(screen.getByText("Flow is healthy.")).toBeInTheDocument());
    expect(screen.getByText("Lower WIP")).toBeInTheDocument();
    expect(screen.getByText(/Work is started faster/)).toBeInTheDocument();
    expect(screen.getByText("wip=12")).toBeInTheDocument();
  });

  it("surfaces an advice generation failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      if (url.startsWith("/api/recommendations/status")) {
        return Promise.resolve(jsonResponse({ configured: true }));
      }
      if (url.startsWith("/api/recommendations")) {
        return Promise.resolve(jsonResponse({ detail: "LLM unavailable" }, 500));
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    renderPage(`/advisor?team=${teamFixture.id}`);

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));

    await waitFor(() => expect(screen.getByText("Failed to generate advice")).toBeInTheDocument());
    expect(screen.getByText("LLM unavailable")).toBeInTheDocument();
  });

  it("shows an error when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderPage();

    await waitFor(() => expect(screen.getByText("Failed to load teams")).toBeInTheDocument());
  });

  it("picks a team from the select and reflects it in the URL", async () => {
    mockFetch();

    renderPage();

    fireEvent.mouseDown((await screen.findAllByRole("combobox"))[0]);
    fireEvent.click(await screen.findByTitle(teamFixture.name));

    await waitFor(() => expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled());
  });

  it("sends the selected persona with the advice request", async () => {
    mockFetch();

    renderPage(`/advisor?team=${teamFixture.id}&persona=delivery_analyst`);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Get advice/ })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Get advice/ }));

    await waitFor(() =>
      expect(vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]))).toContain(
        `/api/recommendations?team_id=${teamFixture.id}&persona=delivery_analyst`,
      ),
    );
  });

  it("surfaces an advisor status failure instead of silently disabling the button", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Failed to load advisor status")).toBeInTheDocument(),
    );
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
