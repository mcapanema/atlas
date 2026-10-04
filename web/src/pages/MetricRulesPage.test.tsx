import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MetricRules, MetricRulesView } from "../api/metricRules";
import { jsonResponse, requestUrl, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { MetricRulesPage } from "./MetricRulesPage";

const ORG = { id: teamFixture.organization_id, name: "Acme", created_at: "2026-07-01T00:00:00Z" };

const BUILT_IN: MetricRules = {
  exclude_born_done: true,
  move_back_ends_wip: true,
  restart_clock_after_move_back: false,
  reopen_completion: "last",
  done_then_canceled: "delivered",
  healthy_min: 70,
  warning_min: 40,
  predictability_worst_ratio: 4,
  stability_best_weeks: 1,
  stability_worst_weeks: 5,
  aging_percentile: 85,
  weight_predictability: 1,
  weight_efficiency: 1,
  weight_flow: 1,
  weight_stability: 1,
  weight_risk: 1,
  timezone: "UTC",
  daily_bucket_max_days: 21,
  forecast_history_days: 90,
};

const IDLE = { state: "idle", started_at: null, finished_at: null, error: null } as const;

function view(changes: Partial<MetricRulesView> = {}): MetricRulesView {
  return {
    built_in: BUILT_IN,
    inherited: BUILT_IN,
    overrides: {},
    effective: BUILT_IN,
    recompute: IDLE,
    ...changes,
  };
}

interface Call {
  url: string;
  method: string;
  body: unknown;
}

function mockApi(current: MetricRulesView, patchStatus = 200): Call[] {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    const method = init?.method ?? "GET";
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    if (url === "/api/organizations") return jsonResponse([ORG]);
    if (url === "/api/teams") return jsonResponse([teamFixture]);
    if (url.includes("/metric-rules")) {
      calls.push({ url, method, body });
      if (method === "PATCH" && patchStatus !== 200) {
        return jsonResponse({ detail: "healthy_min must be between 1 and 100" }, patchStatus);
      }
      return jsonResponse(current);
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });
  return calls;
}

const RESTART = "Restart the clock after a move-back";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("MetricRulesPage", () => {
  it("shows the workspace default with built-in hints and nothing to save", async () => {
    mockApi(view());

    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    expect(await screen.findByText("Lifecycle")).toBeInTheDocument();
    expect(screen.getAllByText(/^Built-in:/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("saves just the rule that changed", async () => {
    const calls = mockApi(view());
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    fireEvent.click(await screen.findByRole("switch", { name: RESTART }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({
        restart_clock_after_move_back: true,
      }),
    );
    expect(calls.find((call) => call.method === "PATCH")?.url).toBe(
      `/api/organizations/${ORG.id}/metric-rules`,
    );
  });

  it("marks a team override and resets it to the workspace default", async () => {
    const calls = mockApi(
      view({
        overrides: { restart_clock_after_move_back: true },
        effective: { ...BUILT_IN, restart_clock_after_move_back: true },
      }),
    );
    renderWithClient(<MetricRulesPage />, [`/metric-rules?team=${teamFixture.id}`]);

    expect(await screen.findByText("Customized")).toBeInTheDocument();
    expect(screen.getAllByText(/^Workspace default:/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Reset to default" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({
        restart_clock_after_move_back: null,
      }),
    );
  });

  it("shows the recompute banner while history is rewritten", async () => {
    mockApi(view({ recompute: { ...IDLE, state: "running", started_at: "2026-10-03T12:00:00Z" } }));

    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    expect(await screen.findByText("Recomputing history…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recompute history" })).toBeDisabled();
  });

  it("shows the banner after a save, polls while running, and clears once idle", async () => {
    const running = view({
      recompute: { ...IDLE, state: "running", started_at: "2026-10-03T12:00:00Z" },
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let current = view();
    const calls = mockApi(current);
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = requestUrl(input);
      if (url === "/api/organizations") return jsonResponse([ORG]);
      if (url === "/api/teams") return jsonResponse([teamFixture]);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: undefined });
      if (method === "PATCH") {
        current = running;
        return jsonResponse(running);
      }
      // the rewrite has finished by the first poll
      current = view();
      return jsonResponse(current);
    });
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    fireEvent.click(await screen.findByRole("switch", { name: RESTART }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Recomputing history…")).toBeInTheDocument();
    const getsAtSave = calls.filter((call) => call.method === "GET").length;
    await vi.advanceTimersByTimeAsync(2_000);
    await waitFor(() => expect(screen.queryByText("Recomputing history…")).not.toBeInTheDocument());
    expect(calls.filter((call) => call.method === "GET").length).toBeGreaterThan(getsAtSave);
  });

  it("shows why a save was rejected", async () => {
    mockApi(view(), 422);
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    fireEvent.click(await screen.findByRole("switch", { name: RESTART }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("healthy_min must be between 1 and 100")).toBeInTheDocument();
  });
});
