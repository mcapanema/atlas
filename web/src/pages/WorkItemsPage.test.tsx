import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, teamFixture, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { WorkItemsPage } from "./WorkItemsPage";

const TEAM_ID = teamFixture.id;

function mockApi() {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = requestUrl(input);
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
            url: "https://linear.app/acme/issue/ENG-1/fix-login-flow",
            created_at: "2026-06-10T14:32:07Z",
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

    // The origin link sits in its own column and opens outside the app.
    const source = screen.getByRole("link", { name: /linear\.app/ });
    expect(source).toHaveAttribute("href", "https://linear.app/acme/issue/ENG-1/fix-login-flow");
    expect(source).toHaveAttribute("target", "_blank");
    expect(source).toHaveAttribute("rel", "noopener noreferrer");

    const calls = vi.mocked(globalThis.fetch).mock.calls.map((call) => requestUrl(call[0]));
    expect(calls.some((url) => url.includes("limit=50") && url.includes("offset=0"))).toBe(true);
  });

  it("reads the team filter and page from the URL", async () => {
    mockApi();

    renderWithClient(<WorkItemsPage />, [`/work-items?team=${TEAM_ID}&page=2`]);

    await waitFor(() => {
      const calls = vi.mocked(globalThis.fetch).mock.calls.map((c) => requestUrl(c[0]));
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

  it("renders an error alert when work items fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
      return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
    });

    renderWithClient(<WorkItemsPage />, ["/work-items"]);

    await waitFor(() => expect(screen.getByText("Failed to load work items")).toBeInTheDocument());
  });

  it("filters by team via the select, then clears the filter", async () => {
    mockApi();

    renderWithClient(<WorkItemsPage />, ["/work-items"]);
    await waitFor(() => expect(screen.getByText("Fix login flow")).toBeInTheDocument());

    fireEvent.mouseDown(screen.getByRole("combobox"));
    fireEvent.click(await screen.findByTitle(teamFixture.name));

    await waitFor(() => {
      const calls = vi.mocked(globalThis.fetch).mock.calls.map((c) => requestUrl(c[0]));
      expect(calls.some((url) => url.includes(`team_id=${TEAM_ID}`))).toBe(true);
    });

    const callsBeforeClear = vi.mocked(globalThis.fetch).mock.calls.length;
    // antd >= 6.6 renders the clear affordance as <button aria-label="Clear">
    // and clears on click (not mouseDown).
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    await waitFor(() => {
      const newCalls = vi
        .mocked(globalThis.fetch)
        .mock.calls.slice(callsBeforeClear)
        .map((c) => requestUrl(c[0]));
      expect(
        newCalls.some((url) => url.includes("/api/work-items?") && !url.includes("team_id")),
      ).toBe(true);
    });
  });

  it("changes page via the table pagination", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = requestUrl(input);
      if (url.startsWith("/api/teams")) return Promise.resolve(jsonResponse([teamFixture]));
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
              url: null,
              created_at: "2026-07-01T00:00:00Z",
            },
          ],
          total: 51,
        }),
      );
    });

    renderWithClient(<WorkItemsPage />, ["/work-items"]);
    await waitFor(() => expect(screen.getByText("Fix login flow")).toBeInTheDocument());

    fireEvent.click(screen.getByTitle("2"));

    await waitFor(() => {
      const calls = vi.mocked(globalThis.fetch).mock.calls.map((c) => requestUrl(c[0]));
      expect(calls.some((url) => url.includes("offset=50"))).toBe(true);
    });
  });

  it("renders the created timestamp as DD-MM-YYYY HH:mm", async () => {
    mockApi();

    renderWithClient(<WorkItemsPage />, ["/work-items"]);
    expect(await screen.findByText("10-06-2026 14:32")).toBeInTheDocument();
  });
});
