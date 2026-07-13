import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { MeetingsPage } from "./MeetingsPage";

const prep = {
  meeting: "daily_standup",
  generated_at: "2026-07-12T00:00:00Z",
  headline: "One item is past the p85 age line.",
  talking_points: [
    {
      point: "Unstick 'Fix login'",
      detail: "In progress 6 days against a 4-day p85.",
      evidence: ["cycle-time p85 = 4.0d"],
      needs_decision: true,
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
    if (url.startsWith("/api/personas") && url.endsWith("/guidance")) {
      return Promise.resolve(jsonResponse([]));
    }
    if (url.startsWith("/api/personas") && url.endsWith("/feedback")) {
      return Promise.resolve(
        jsonResponse(
          {
            id: "f-1",
            persona: "daily_standup",
            rating: "up",
            comment: null,
            advice_summary: prep.headline,
            created_at: "2026-07-12T00:00:00Z",
          },
          201,
        ),
      );
    }
    if (url.startsWith("/api/meetings/prep")) return Promise.resolve(jsonResponse(prep));
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
}

function renderPage(initialEntry = "/meetings") {
  return renderWithClient(<MeetingsPage />, [initialEntry]);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MeetingsPage", () => {
  it("warns when the advisor is not configured", async () => {
    mockFetch({ configured: false });

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/Meeting prep is not configured/)).toBeInTheDocument(),
    );
  });

  it("does not fetch a prep until the button is clicked", async () => {
    mockFetch();

    renderPage(`/meetings?team=${teamFixture.id}`);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Prepare meeting/ })).toBeEnabled(),
    );
    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.startsWith("/api/meetings/prep"))).toBe(false);
  });

  it("renders headline and talking points after clicking Prepare meeting", async () => {
    mockFetch();

    renderPage(`/meetings?team=${teamFixture.id}`);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Prepare meeting/ })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Prepare meeting/ }));

    await waitFor(() =>
      expect(screen.getByText("One item is past the p85 age line.")).toBeInTheDocument(),
    );
    expect(screen.getByText("Unstick 'Fix login'")).toBeInTheDocument();
    expect(screen.getByText("needs decision")).toBeInTheDocument();
    expect(screen.getByText("cycle-time p85 = 4.0d")).toBeInTheDocument();
    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain(
      `/api/meetings/prep?team_id=${teamFixture.id}&meeting=daily_standup`,
    );
  });

  it("sends retro sprint days as window_days", async () => {
    mockFetch();

    renderPage(`/meetings?team=${teamFixture.id}&meeting=retrospective`);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Prepare meeting/ })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Prepare meeting/ }));

    await waitFor(() =>
      expect(
        vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0])),
      ).toContain(
        `/api/meetings/prep?team_id=${teamFixture.id}&meeting=retrospective&window_days=14`,
      ),
    );
  });

  it("sends planning what-ifs with the request", async () => {
    mockFetch();

    renderPage(`/meetings?team=${teamFixture.id}&meeting=planning`);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Prepare meeting/ })).toBeEnabled(),
    );
    fireEvent.change(screen.getByPlaceholderText("Planned scope (items)"), {
      target: { value: "8" },
    });
    fireEvent.change(screen.getByLabelText("Target date"), {
      target: { value: "2026-08-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Prepare meeting/ }));

    await waitFor(() =>
      expect(
        vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0])),
      ).toContain(
        `/api/meetings/prep?team_id=${teamFixture.id}&meeting=planning&remaining=8&target_date=2026-08-01`,
      ),
    );
  });

  it("surfaces a prep generation failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      if (url.startsWith("/api/recommendations/status")) {
        return Promise.resolve(jsonResponse({ configured: true }));
      }
      if (url.startsWith("/api/personas") && url.endsWith("/guidance")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.startsWith("/api/meetings/prep")) {
        return Promise.resolve(jsonResponse({ detail: "LLM unavailable" }, 500));
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    renderPage(`/meetings?team=${teamFixture.id}`);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Prepare meeting/ })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Prepare meeting/ }));

    await waitFor(() =>
      expect(screen.getByText("Failed to generate meeting prep")).toBeInTheDocument(),
    );
    expect(screen.getByText("LLM unavailable")).toBeInTheDocument();
  });

  it("submits feedback to the meeting persona with the prep headline", async () => {
    mockFetch();

    renderPage(`/meetings?team=${teamFixture.id}`);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Prepare meeting/ })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Prepare meeting/ }));
    await waitFor(() =>
      expect(screen.getByText("One item is past the p85 age line.")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));

    await waitFor(() =>
      expect(screen.getByText(/Thanks for the feedback/)).toBeInTheDocument(),
    );
    const call = vi
      .mocked(globalThis.fetch)
      .mock.calls.find((c) => String(c[0]).endsWith("/feedback"));
    expect(String(call![0])).toBe("/api/personas/daily_standup/feedback");
    expect(JSON.parse(String(call![1]!.body))).toEqual({
      rating: "up",
      comment: null,
      advice_summary: "One item is past the p85 age line.",
    });
  });

  it("shows an error when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderPage();

    await waitFor(() => expect(screen.getByText("Failed to load teams")).toBeInTheDocument());
  });
});
