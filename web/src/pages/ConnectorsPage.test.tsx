import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { ConnectorsPage } from "./ConnectorsPage";

function mockApi({ configured }: { configured: boolean }) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/connectors/linear") return jsonResponse({ configured });
    if (url === "/api/organizations")
      return jsonResponse([
        {
          id: "11111111-1111-1111-1111-111111111111",
          name: "Acme",
          created_at: "2026-07-01T00:00:00Z",
        },
      ]);
    if (url === "/api/connectors/linear/sync")
      return jsonResponse({ teams: 1, projects: 2, work_items: 3, events: 42, divergences: 7 });
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ConnectorsPage", () => {
  it("shows configured status and displays sync results", async () => {
    mockApi({ configured: true });

    renderWithClient(<ConnectorsPage />);

    await waitFor(() => expect(screen.getByText("Configured")).toBeInTheDocument());
    const button = await screen.findByRole("button", { name: "Sync now" });
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);

    await waitFor(() => expect(screen.getByText("42")).toBeInTheDocument());
    expect(screen.getByText("Divergences")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("shows setup instructions and disables sync when not configured", async () => {
    mockApi({ configured: false });

    renderWithClient(<ConnectorsPage />);

    await waitFor(() =>
      expect(screen.getByText(/ATLAS_LINEAR_API_KEY/)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Sync now" })).toBeDisabled();
  });

  it("shows an error instead of 'Not configured' when the status fetch fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
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
});
