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
  count_parent_issues: true,
  lead_time_start: "created",
  done_then_reopened: "delivered",
  canceled_then_reopened: "canceled",
  blocked_label_pattern: true,
  blocked_label_names: [],
  blocked_by_relations: false,
  remaining_state_types: ["triage", "backlog", "unstarted", "started"],
  type_labels: [],
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

function mockApi(
  current: MetricRulesView,
  patchStatus = 200,
  extra: { recomputeStatus?: number; organizations?: (typeof ORG)[] } = {},
): Call[] {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    const method = init?.method ?? "GET";
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    if (url === "/api/organizations") return jsonResponse(extra.organizations ?? [ORG]);
    if (url === "/api/teams") return jsonResponse([teamFixture]);
    if (url.startsWith("/api/work-items/labels")) return jsonResponse(["Blocked", "Bug"]);
    if (url.includes("/metric-rules")) {
      calls.push({ url, method, body });
      if (method === "POST" && extra.recomputeStatus) {
        return jsonResponse({ detail: "recompute is unavailable" }, extra.recomputeStatus);
      }
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

// Every test here drives the full rules form through AntD: 0.3–0.6 s idle,
// but they crossed Vitest's 5 s default on CPU-starved runs (CI on main run
// 37612629650 and PR #106; locally under coverage). Assertions unchanged.
describe("MetricRulesPage", { timeout: 15_000 }, () => {
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

  it("shows the Blocked and Work item types groups", async () => {
    mockApi(view());

    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    expect(await screen.findByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Count Linear 'blocked by' relations")).toBeInTheDocument();
    expect(screen.getByText("Work item types")).toBeInTheDocument();
  });

  it("shows the recompute banner while history is rewritten, and lets you restart it", async () => {
    mockApi(view({ recompute: { ...IDLE, state: "running", started_at: "2026-10-03T12:00:00Z" } }));

    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    expect(await screen.findByText("Recomputing history…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recompute history" })).toBeEnabled();
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
      if (url.startsWith("/api/work-items/labels")) return jsonResponse(["Blocked", "Bug"]);
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

  it("offers a retry that recomputes the team's organization", async () => {
    const calls = mockApi(view({ recompute: { ...IDLE, state: "failed", error: "boom" } }));
    renderWithClient(<MetricRulesPage />, [`/metric-rules?team=${teamFixture.id}`]);

    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(await screen.findByTitle(teamFixture.name)).toBeInTheDocument(); // teams loaded
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() =>
      expect(
        calls.some(
          (call) =>
            call.method === "POST" &&
            call.url === `/api/organizations/${ORG.id}/metric-rules/recompute`,
        ),
      ).toBe(true),
    );
  });

  it("shows why a save was rejected", async () => {
    mockApi(view(), 422);
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    fireEvent.click(await screen.findByRole("switch", { name: RESTART }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("healthy_min must be between 1 and 100")).toBeInTheDocument();
  });

  it("keeps Retry disabled until the team's organization is known", async () => {
    const calls = mockApi(view({ recompute: { ...IDLE, state: "failed", error: "boom" } }));
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = requestUrl(input);
      if (url === "/api/organizations") return jsonResponse([ORG]);
      if (url === "/api/teams") return new Promise<Response>(() => undefined); // never loads
      if (url.startsWith("/api/work-items/labels")) return jsonResponse([]);
      return jsonResponse(view({ recompute: { ...IDLE, state: "failed", error: "boom" } }));
    });
    renderWithClient(<MetricRulesPage />, [`/metric-rules?team=${teamFixture.id}`]);

    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(retry).toBeDisabled();
    fireEvent.click(retry);
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(0);
  });

  it("shows why a recompute could not start", async () => {
    mockApi(view(), 200, { recomputeStatus: 500 });
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    fireEvent.click(await screen.findByRole("button", { name: "Recompute history" }));

    expect(await screen.findByText("recompute is unavailable")).toBeInTheDocument();
  });

  it("drops a recompute error when the scope switches", async () => {
    mockApi(view(), 200, { recomputeStatus: 500 });
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);
    fireEvent.click(await screen.findByRole("button", { name: "Recompute history" }));
    expect(await screen.findByText("recompute is unavailable")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Rules for" }));
    fireEvent.click(await screen.findByTitle(teamFixture.name));

    await waitFor(() => expect(screen.queryByText("recompute is unavailable")).toBeNull());
  });

  it("treats toggling a rule back to its inherited value as no change", async () => {
    const calls = mockApi(view());
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    const toggle = await screen.findByRole("switch", { name: RESTART });
    fireEvent.click(toggle);
    expect(await screen.findByText("Customized")).toBeInTheDocument();
    fireEvent.click(toggle);

    await waitFor(() => expect(screen.queryByText("Customized")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(calls.some((call) => call.method === "PATCH")).toBe(false);
  });

  it("confirms before a scope switch drops unsaved edits", async () => {
    mockApi(view());
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);
    fireEvent.click(await screen.findByRole("switch", { name: RESTART }));

    const pickTeam = async () => {
      fireEvent.mouseDown(screen.getByRole("combobox", { name: "Rules for" }));
      fireEvent.click(await screen.findByTitle(teamFixture.name));
    };
    await pickTeam();
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(screen.getAllByText(/^Built-in:/).length).toBeGreaterThan(0); // scope kept
    expect(screen.getByRole("switch", { name: RESTART })).toBeChecked(); // draft kept
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();

    await pickTeam();
    // the cancelled dialog may still be animating out, so take the newest one
    const confirms = await screen.findAllByRole("button", { name: "Discard and switch" });
    fireEvent.click(confirms[confirms.length - 1]);

    expect(await screen.findAllByText(/^Workspace default:/)).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("switches scope straight away when nothing is unsaved", async () => {
    mockApi(view());
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);
    await screen.findByText("Lifecycle");

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Rules for" }));
    fireEvent.click(await screen.findByTitle(teamFixture.name));

    expect(await screen.findAllByText(/^Workspace default:/)).not.toHaveLength(0);
    expect(screen.queryByText("Discard unsaved changes?")).toBeNull();
  });

  it("forgets unsaved edits once the form is gone, even before the next scope loads", async () => {
    mockApi(view());
    const respond = vi.mocked(globalThis.fetch).getMockImplementation();
    vi.mocked(globalThis.fetch).mockImplementation((input, init) =>
      requestUrl(input).startsWith("/api/teams/")
        ? new Promise<Response>(() => undefined) // the team's rules never load
        : respond!(input, init),
    );
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);
    fireEvent.click(await screen.findByRole("switch", { name: RESTART }));

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Rules for" }));
    fireEvent.click(await screen.findByTitle(teamFixture.name));
    fireEvent.click(await screen.findByRole("button", { name: "Discard and switch" }));
    await waitFor(() => expect(screen.queryByRole("switch", { name: RESTART })).toBeNull());

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Rules for" }));
    fireEvent.click(await screen.findByTitle(`Workspace default — ${ORG.name}`));

    await waitFor(() => expect(screen.getByRole("switch", { name: RESTART })).toBeInTheDocument());
  });

  it("shows an empty state when there are no organizations", async () => {
    mockApi(view(), 200, { organizations: [] });
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    expect(await screen.findByText(/No organizations yet/)).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Rules for" })).not.toBeInTheDocument();
  });

  it("explains when the restart clock applies", async () => {
    mockApi(view());
    renderWithClient(<MetricRulesPage />, ["/metric-rules"]);

    expect(
      await screen.findByText(
        /only while "Moving back to backlog ends WIP" is on, and always after a cancel/,
      ),
    ).toBeInTheDocument();
  });
});
