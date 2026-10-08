import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SyncSchedule } from "../api/syncSchedule";
import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { SyncStatus } from "./SyncStatus";

const ORG = "11111111-1111-1111-1111-111111111111";
const SCHEDULE_URL = `/api/organizations/${ORG}/sync-schedule`;

const schedule: SyncSchedule = {
  enabled: true,
  days: [1, 3],
  window_start: "09:00:00",
  window_end: "17:00:00",
  interval_minutes: 60,
  timezone: "UTC",
  updated_at: "2026-10-07T12:00:00Z",
  last_run: null,
  last_manual_sync_at: null,
  next_run_at: "2026-10-08T09:00:00Z",
};

const failedRun = {
  slot_at: "2026-10-07T09:00:00Z",
  finished_at: "2026-10-07T09:01:00Z",
  error: "Upstream data source error: rate limited",
};

function mockSchedule(body: SyncSchedule | null) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = requestUrl(input);
    if (url !== SCHEDULE_URL) throw new Error(`Unexpected fetch: ${url}`);
    return jsonResponse(body);
  });
}

afterEach(() => vi.restoreAllMocks());

describe("SyncStatus", () => {
  it("shows the next run in the schedule's zone, not the browser's", async () => {
    mockSchedule({
      ...schedule,
      timezone: "America/Sao_Paulo",
      next_run_at: "2026-10-08T11:00:00Z",
    });

    renderWithClient(<SyncStatus organizationId={ORG} />);

    expect(await screen.findByText("08-10-2026 08:00 (America/Sao_Paulo)")).toBeInTheDocument();
  });

  it("shows a successful auto run as the last sync", async () => {
    mockSchedule({ ...schedule, last_run: { ...failedRun, error: null } });

    renderWithClient(<SyncStatus organizationId={ORG} />);

    expect(await screen.findByText("07-10-2026 09:01 (UTC) · auto")).toBeInTheDocument();
    expect(screen.queryByText("Last auto sync failed")).not.toBeInTheDocument();
  });

  it("flags a failed auto run with its reason", async () => {
    mockSchedule({ ...schedule, last_run: failedRun });

    renderWithClient(<SyncStatus organizationId={ORG} />);

    expect(await screen.findByText("Failed · 07-10-2026 09:01 (UTC)")).toBeInTheDocument();
    expect(screen.getByText("Last auto sync failed")).toBeInTheDocument();
    expect(screen.getByText("Upstream data source error: rate limited")).toBeInTheDocument();
  });

  it("drops a stale failure once a manual sync succeeds after it", async () => {
    mockSchedule({ ...schedule, last_run: failedRun, last_manual_sync_at: "2026-10-07T10:00:00Z" });

    renderWithClient(<SyncStatus organizationId={ORG} />);

    expect(await screen.findByText("07-10-2026 10:00 (UTC) · manual")).toBeInTheDocument();
    expect(screen.queryByText("Last auto sync failed")).not.toBeInTheDocument();
  });

  it("doesn't claim 'Never' for a schedule row with no sync recorded on it", async () => {
    // A Sync now before the row existed went unrecorded, so an empty row
    // can't tell "never synced" from "synced before recording began".
    mockSchedule({ ...schedule, enabled: false, next_run_at: null });

    renderWithClient(<SyncStatus organizationId={ORG} />);

    expect(await screen.findByText("Auto sync is off")).toBeInTheDocument();
    expect(screen.getByText("Not recorded")).toBeInTheDocument();
    expect(screen.queryByText("Never")).not.toBeInTheDocument();
  });

  it("doesn't claim 'Never' when no schedule row exists to record syncs", async () => {
    mockSchedule(null);

    renderWithClient(<SyncStatus organizationId={ORG} />);

    expect(await screen.findByText("Not scheduled")).toBeInTheDocument();
    expect(screen.getByText("Not recorded")).toBeInTheDocument();
    expect(screen.queryByText("Never")).not.toBeInTheDocument();
  });

  it("renders nothing when the schedule fails to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "boom" }, 500));

    const { container } = renderWithClient(<SyncStatus organizationId={ORG} />);

    await vi.waitFor(() => expect(container.querySelector(".ant-skeleton")).toBeNull());
    expect(screen.queryByText("Last sync")).not.toBeInTheDocument();
  });
});
