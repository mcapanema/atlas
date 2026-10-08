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

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TeamSyncButton", () => {
  it("syncs the team and reports what changed", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(summary));

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(await screen.findByText("Updated 3 work items · 12 events")).toBeInTheDocument();
    const [input, init] = fetchMock.mock.calls[0];
    expect(requestUrl(input)).toBe(`/api/connectors/linear/teams/${syncedTeam.id}/sync`);
    expect(init?.method).toBe("POST");
  });

  it("says when the team was already up to date", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ ...summary, work_items: 0, events: 0 }),
    );

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(await screen.findByText("Already up to date")).toBeInTheDocument();
  });

  it("shows the server's reason when the sync fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Linear is not configured" }, 409),
    );

    renderWithClient(<TeamSyncButton team={syncedTeam} />);
    fireEvent.click(screen.getByRole("button", { name: /Sync team/ }));

    expect(await screen.findByText("Linear is not configured")).toBeInTheDocument();
  });

  it("is disabled for a team made in Atlas", () => {
    renderWithClient(<TeamSyncButton team={teamFixture} />);

    expect(screen.getByRole("button", { name: /Sync team/ })).toBeDisabled();
  });
});
