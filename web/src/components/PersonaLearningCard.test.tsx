import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { PersonaLearningCard } from "./PersonaLearningCard";

const v1 = {
  persona: "agile_coach",
  version: 1,
  guidance: "Be concise.",
  created_at: "2026-07-11T00:00:00Z",
};
const v2 = {
  persona: "agile_coach",
  version: 2,
  guidance: "Lead with WIP limits.",
  created_at: "2026-07-12T00:00:00Z",
};

function mockGuidanceFetch(
  versions: unknown[],
  { reflectStatus = 201 }: { reflectStatus?: number } = {},
) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url === "/api/personas/agile_coach/guidance" && method === "GET") {
      return Promise.resolve(jsonResponse(versions));
    }
    if (url === "/api/personas/agile_coach/reflect" && method === "POST") {
      if (reflectStatus !== 201) {
        return Promise.resolve(
          jsonResponse({ detail: "No new feedback to reflect on" }, reflectStatus),
        );
      }
      return Promise.resolve(jsonResponse(v2, 201));
    }
    if (url === "/api/personas/agile_coach/guidance/1/restore" && method === "POST") {
      return Promise.resolve(jsonResponse({ ...v1, version: 3 }, 201));
    }
    return Promise.reject(new Error(`Unexpected fetch: ${method} ${url}`));
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PersonaLearningCard", () => {
  it("shows the empty state before any reflection", async () => {
    mockGuidanceFetch([]);

    renderWithClient(<PersonaLearningCard persona="agile_coach" />);

    await waitFor(() =>
      expect(screen.getByText(/No learned guidance yet/)).toBeInTheDocument(),
    );
  });

  it("shows the latest guidance and older versions", async () => {
    mockGuidanceFetch([v2, v1]);

    renderWithClient(<PersonaLearningCard persona="agile_coach" />);

    await waitFor(() =>
      expect(screen.getByText("Lead with WIP limits.")).toBeInTheDocument(),
    );
    expect(screen.getByText(/v2/)).toBeInTheDocument();
    expect(screen.getByText(/v1: Be concise\./)).toBeInTheDocument();
  });

  it("reflects on demand", async () => {
    mockGuidanceFetch([]);

    renderWithClient(<PersonaLearningCard persona="agile_coach" />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reflect now/ })).toBeEnabled(),
    );

    fireEvent.click(screen.getByRole("button", { name: /Reflect now/ }));

    await waitFor(() => {
      const calls = vi.mocked(globalThis.fetch).mock.calls;
      expect(
        calls.some(
          (c) =>
            String(c[0]) === "/api/personas/agile_coach/reflect" && c[1]?.method === "POST",
        ),
      ).toBe(true);
    });
  });

  it("surfaces a reflect failure", async () => {
    mockGuidanceFetch([], { reflectStatus: 409 });

    renderWithClient(<PersonaLearningCard persona="agile_coach" />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reflect now/ })).toBeEnabled(),
    );

    fireEvent.click(screen.getByRole("button", { name: /Reflect now/ }));

    await waitFor(() => expect(screen.getByText("Reflection failed")).toBeInTheDocument());
    expect(screen.getByText("No new feedback to reflect on")).toBeInTheDocument();
  });

  it("restores an older version", async () => {
    mockGuidanceFetch([v2, v1]);

    renderWithClient(<PersonaLearningCard persona="agile_coach" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Restore" })).toBeEnabled());

    fireEvent.click(screen.getByRole("button", { name: "Restore" }));

    await waitFor(() => {
      const calls = vi.mocked(globalThis.fetch).mock.calls;
      expect(
        calls.some(
          (c) => String(c[0]) === "/api/personas/agile_coach/guidance/1/restore",
        ),
      ).toBe(true);
    });
  });
});
