import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { OrganizationsPage } from "./OrganizationsPage";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OrganizationsPage", () => {
  it("renders organizations returned by the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([
        { id: "11111111-1111-1111-1111-111111111111", name: "Acme", created_at: "2026-07-08T00:00:00Z" },
      ]),
    );

    renderWithClient(<OrganizationsPage />);

    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
  });

  it("shows an error when organizations fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderWithClient(<OrganizationsPage />);

    await waitFor(() =>
      expect(screen.getByText("Failed to load organizations")).toBeInTheDocument(),
    );
  });
});
