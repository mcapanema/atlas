import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { ConnectorsPage } from "./ConnectorsPage";

const ACME = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Acme",
  created_at: "2026-07-01T00:00:00Z",
};
const GLOBEX = {
  id: "22222222-2222-2222-2222-222222222222",
  name: "Globex",
  created_at: "2026-07-02T00:00:00Z",
};

function mockApi({
  configured,
  autoSyncing = false,
  organizations = [ACME],
  statusPending = false,
}: {
  configured: boolean;
  autoSyncing?: boolean;
  organizations?: (typeof ACME)[];
  statusPending?: boolean;
}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    if (url === "/api/connectors/linear")
      return statusPending
        ? new Promise<Response>(() => {})
        : jsonResponse({ configured, auto_syncing: autoSyncing });
    if (url === "/api/organizations") return jsonResponse(organizations);
    if (url === "/api/connectors/linear/sync")
      return jsonResponse({
        teams: 1,
        projects: 2,
        work_items: 3,
        events: 42,
        divergences: 7,
        deleted: 9,
      });
    if (url.endsWith("/sync-schedule") && init?.method === "PUT")
      return jsonResponse({
        ...(JSON.parse(init.body as string) as object),
        updated_at: "2026-10-07T13:00:00Z",
        last_run: null,
        last_manual_sync_at: null,
        next_run_at: null,
      });
    if (url.endsWith("/sync-schedule")) return jsonResponse(null);
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("ConnectorsPage", () => {
  it("shows configured status and the sync outcome in one line", async () => {
    mockApi({ configured: true });

    renderWithClient(<ConnectorsPage />);

    expect(await screen.findByText("Configured")).toBeInTheDocument();
    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);

    expect(
      await screen.findByText(
        "Updated 1 team · 2 projects · 3 work items · 42 events · 9 work items removed",
      ),
    ).toBeInTheDocument();
  });

  it("shows the sync status and the auto-sync card for the selected organization", async () => {
    mockApi({ configured: true });

    renderWithClient(<ConnectorsPage />);

    expect(await screen.findByText("Next run")).toBeInTheDocument();
    expect(await screen.findByText("Not scheduled")).toBeInTheDocument();
    expect(screen.getByText("Auto sync")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Save schedule" })).toBeInTheDocument();
  });

  it("says why Sync now waits while an automatic sync runs", async () => {
    mockApi({ configured: true, autoSyncing: true });

    renderWithClient(<ConnectorsPage />);

    expect(
      await screen.findByText(/An automatic sync is running; Sync now starts when it finishes/),
    ).toBeInTheDocument();
  });

  it("polls the Linear status so a running auto sync shows up", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = mockApi({ configured: true });
    const statusCalls = () =>
      fetchMock.mock.calls.filter(([input]) => requestUrl(input) === "/api/connectors/linear")
        .length;

    renderWithClient(<ConnectorsPage />);
    await waitFor(() => expect(statusCalls()).toBe(1));

    await vi.advanceTimersByTimeAsync(15_000);

    await waitFor(() => expect(statusCalls()).toBe(2));
  });

  it("does not carry a saved message over to another organization", async () => {
    mockApi({ configured: true, organizations: [ACME, GLOBEX] });

    renderWithClient(<ConnectorsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Save schedule" }));
    expect(await screen.findByText("Schedule saved")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Organization" }));
    fireEvent.click(await screen.findByTitle("Globex"));

    // Globex has no schedule: wait for its form, not the loading skeleton.
    expect(await screen.findByText("Not scheduled")).toBeInTheDocument();
    expect(screen.queryByText("Schedule saved")).not.toBeInTheDocument();
  });

  it("warns once, at page level, and disables sync when not configured", async () => {
    mockApi({ configured: false });

    renderWithClient(<ConnectorsPage />);

    expect(await screen.findByText("Linear isn't configured")).toBeInTheDocument();
    expect(screen.getAllByText("ATLAS_LINEAR_API_KEY")).toHaveLength(1);
    expect(screen.getByText(/scheduled syncs fail/)).toBeInTheDocument();
    expect(screen.getByText("Not configured")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Sync now/ })).toBeDisabled();
  });

  it("neither warns nor says 'Not configured' while the status is unknown", async () => {
    mockApi({ configured: false, statusPending: true });

    renderWithClient(<ConnectorsPage />);

    expect(await screen.findByText("Connectors")).toBeInTheDocument();
    expect(screen.queryByText("Linear isn't configured")).not.toBeInTheDocument();
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
  });

  it("refreshes the last sync after Sync now", async () => {
    const fetchMock = mockApi({ configured: true });
    const scheduleReads = () =>
      fetchMock.mock.calls.filter(
        ([input, init]) => requestUrl(input).endsWith("/sync-schedule") && init?.method !== "PUT",
      ).length;

    renderWithClient(<ConnectorsPage />);
    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());
    await waitFor(() => expect(scheduleReads()).toBe(1));

    fireEvent.click(button);

    await waitFor(() => expect(scheduleReads()).toBe(2));
  });

  it("shows an error when sync fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = requestUrl(input);
      if (url === "/api/connectors/linear") return jsonResponse({ configured: true });
      if (url === "/api/organizations")
        return jsonResponse([
          {
            id: "11111111-1111-1111-1111-111111111111",
            name: "Acme",
            created_at: "2026-07-01T00:00:00Z",
          },
        ]);
      if (url === "/api/connectors/linear/sync") return jsonResponse({ detail: "boom" }, 500);
      if (url.endsWith("/sync-schedule")) return jsonResponse(null);
      throw new Error(`Unexpected fetch: ${url}`);
    });

    renderWithClient(<ConnectorsPage />);

    const button = await screen.findByRole("button", { name: /Sync now/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() => expect(screen.getByText("Sync failed")).toBeInTheDocument());
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("shows an error instead of 'Not configured' when the status fetch fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = requestUrl(input);
      if (url === "/api/connectors/linear") {
        return jsonResponse({ detail: "boom" }, 500);
      }
      if (url === "/api/organizations") return jsonResponse([]);
      throw new Error(`Unexpected fetch: ${url}`);
    });

    renderWithClient(<ConnectorsPage />);

    await waitFor(() =>
      expect(screen.getByText("Failed to load connector status")).toBeInTheDocument(),
    );
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
  });

  it("enables sync with no organizations and bootstraps one from Linear", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = requestUrl(input);
      if (url === "/api/connectors/linear") return jsonResponse({ configured: true });
      if (url === "/api/organizations") return jsonResponse([]);
      if (url === "/api/connectors/linear/sync") {
        expect(JSON.parse(init?.body as string)).toEqual({ organization_id: null });
        return jsonResponse({
          teams: 1,
          projects: 0,
          work_items: 0,
          events: 0,
          divergences: 0,
          deleted: 0,
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });

    renderWithClient(<ConnectorsPage />);

    await waitFor(() => expect(screen.getByText(/first sync will create/i)).toBeInTheDocument());
    expect(screen.queryByRole("combobox", { name: "Organization" })).not.toBeInTheDocument();
    const button = await screen.findByRole("button", { name: /Sync now/ });
    expect(button).toBeEnabled();

    fireEvent.click(button);

    expect(await screen.findByText("Updated 1 team")).toBeInTheDocument();
    const orgCalls = fetchMock.mock.calls.filter(
      (call) => requestUrl(call[0]) === "/api/organizations",
    );
    expect(orgCalls.length).toBeGreaterThan(1); // invalidated + refetched after sync
  });
});
