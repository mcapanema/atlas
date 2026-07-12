import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, metricsFixture, mockMetricsFetch, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { ExecutiveDashboardPage } from "./ExecutiveDashboardPage";

const teams = [
  teamFixture,
  { ...teamFixture, id: "55555555-5555-5555-5555-555555555555", name: "Growth" },
];

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ExecutiveDashboardPage", () => {
  it("lists every team with its flow metrics, linking to its dashboard", async () => {
    // Distinct completed counts per team so the test can catch a metrics/team
    // mismatch (e.g. an off-by-one indexing metrics[index] against teams).
    const platformMetrics = { ...metricsFixture, completed: 4 };
    const growthMetrics = { ...metricsFixture, completed: 9 };
    mockMetricsFetch({
      "/api/teams": teams,
      [`/api/metrics?team_id=${teams[0].id}`]: platformMetrics,
      [`/api/metrics?team_id=${teams[1].id}`]: growthMetrics,
    });

    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(() => expect(screen.getByText("Platform")).toBeInTheDocument());
    expect(screen.getByText("Growth")).toBeInTheDocument();

    const platformRow = screen.getByText("Platform").closest("tr");
    const growthRow = screen.getByText("Growth").closest("tr");
    if (!platformRow || !growthRow) throw new Error("Expected team rows to render");
    await waitFor(() => expect(within(platformRow).getByText("4")).toBeInTheDocument());
    expect(within(growthRow).getByText("9")).toBeInTheDocument();
    expect(within(platformRow).getByText("75%")).toBeInTheDocument();
    expect(within(growthRow).getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("Platform").closest("a")).toHaveAttribute(
      "href",
      `/teams?team=${teams[0].id}`,
    );

    const urls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
    expect(urls).toContain(`/api/metrics?team_id=${teams[0].id}`);
    expect(urls).toContain(`/api/metrics?team_id=${teams[1].id}`);
  });

  it("surfaces teams whose metrics failed to load instead of showing em dashes", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse(teams));
      if (url.startsWith(`/api/metrics?team_id=${teams[0].id}`)) {
        return Promise.resolve(jsonResponse(metricsFixture));
      }
      return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
    });

    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(() =>
      expect(screen.getByText("Metrics failed to load for 1 team")).toBeInTheDocument(),
    );
  });

  it("pluralizes the failed-metrics message for more than one team", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse(teams));
      return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
    });

    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(() =>
      expect(screen.getByText("Metrics failed to load for 2 teams")).toBeInTheDocument(),
    );
  });

  it("shows an error when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderWithClient(<ExecutiveDashboardPage />);

    await waitFor(() => expect(screen.getByText("Failed to load teams")).toBeInTheDocument());
  });

  it("shows per-team forecast accuracy", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });
    renderWithClient(<ExecutiveDashboardPage />);

    expect(await screen.findByText("Forecast accuracy (P85)")).toBeInTheDocument();
    expect(await screen.findByText("90%")).toBeInTheDocument();
  });

  it("shows per-team delivery health", async () => {
    mockMetricsFetch({ "/api/teams": [teamFixture] });

    renderWithClient(<ExecutiveDashboardPage />);

    expect(await screen.findByText("Health")).toBeInTheDocument();
    expect(await screen.findByText("82")).toBeInTheDocument();
  });
});
