import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { TeamSyncButton } from "./TeamSyncButton";

const syncedTeam = { ...teamFixture, external_id: "lt1" };
const summary = {
  teams: 0,
  projects: 0,
  work_items: 3,
  events: 12,
  divergences: 0,
  deleted: 0,
};

/** Connector status + the team-sync POST; a fresh Response per call (a body reads once). */
function mockApi({
  autoSyncing = false,
  sync = () => jsonResponse(summary),
}: { autoSyncing?: boolean; sync?: () => Response } = {}) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation((input) =>
      Promise.resolve(
        requestUrl(input) === "/api/connectors/linear"
          ? jsonResponse({ configured: true, auto_syncing: autoSyncing })
          : sync(),
      ),
    );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TeamSyncButton", () => {
  it("syncs the team and reports what changed", async () => {
    const fetchMock = mockApi();

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(await screen.findByText("Updated 3 work items · 12 events")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post && requestUrl(post[0])).toBe(`/api/connectors/linear/teams/${syncedTeam.id}/sync`);
    // The status query was fetched first and settled by now: no auto sync, no hint.
    expect(screen.queryByText(/An automatic sync is running/)).not.toBeInTheDocument();
  });

  it("says when the team was already up to date", async () => {
    mockApi({ sync: () => jsonResponse({ ...summary, work_items: 0, events: 0 }) });

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(await screen.findByText("Already up to date")).toBeInTheDocument();
  });

  it("shows the server's reason when the sync fails", async () => {
    mockApi({ sync: () => jsonResponse({ detail: "Linear is not configured" }, 409) });

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(await screen.findByText("Linear is not configured")).toBeInTheDocument();
  });

  it("is disabled for a team made in Atlas", () => {
    mockApi();

    renderWithClient(<TeamSyncButton team={teamFixture} />);

    expect(screen.getByRole("button", { name: /Sync team/ })).toBeDisabled();
  });

  it("says why the sync waits while an automatic sync runs", async () => {
    mockApi({ autoSyncing: true });

    renderWithClient(<TeamSyncButton team={syncedTeam} />);

    expect(
      await screen.findByText("An automatic sync is running; Sync team starts when it finishes."),
    ).toBeInTheDocument();
  });
});
