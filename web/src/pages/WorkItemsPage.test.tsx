import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { WorkItemsPage } from "./WorkItemsPage";

const TEAM_ID = teamFixture.id;

function mockApi() {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.startsWith("/api/teams")) {
      return Promise.resolve(jsonResponse([teamFixture]));
    }
    return Promise.resolve(
      jsonResponse({
        items: [
          {
            id: "11111111-1111-1111-1111-111111111111",
            team_id: TEAM_ID,
            project_id: null,
            title: "Fix login flow",
            type: "bug",
            state: "In Progress",
            external_id: null,
            created_at: "2026-07-01T00:00:00Z",
          },
        ],
        total: 1,
      }),
    );
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WorkItemsPage", () => {
  it("renders work items returned by the API", async () => {
    mockApi();

    renderWithClient(<WorkItemsPage />, ["/work-items"]);

    await waitFor(() => expect(screen.getByText("Fix login flow")).toBeInTheDocument());
    expect(screen.getByText("In Progress")).toBeInTheDocument();
    expect(screen.getByText("Fix login flow").closest("a")).toHaveAttribute(
      "href",
      "/work-items/11111111-1111-1111-1111-111111111111",
    );

    const calls = vi.mocked(globalThis.fetch).mock.calls.map((call) => String(call[0]));
    expect(
      calls.some((url) => url.includes("limit=50") && url.includes("offset=0")),
    ).toBe(true);
  });

  it("reads the team filter and page from the URL", async () => {
    mockApi();

    renderWithClient(<WorkItemsPage />, [`/work-items?team=${TEAM_ID}&page=2`]);

    await waitFor(() => {
      const calls = vi.mocked(globalThis.fetch).mock.calls.map((c) => String(c[0]));
      expect(
        calls.some((url) => url.includes(`team_id=${TEAM_ID}`) && url.includes("offset=50")),
      ).toBe(true);
    });
  });

  it("renders an error alert when teams fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 500 }));

    renderWithClient(<WorkItemsPage />, ["/work-items"]);

    await waitFor(() => expect(screen.getByText("Failed to load teams")).toBeInTheDocument());
  });
});
