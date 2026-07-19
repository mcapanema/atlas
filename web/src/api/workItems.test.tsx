import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test/fixtures";
import { useWorkItemStates } from "./workItems";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useWorkItemStates", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requests the team-scoped states", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse(["backlog", "done"]));

    const { result } = renderHook(() => useWorkItemStates({ teamId: "t1" }), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual(["backlog", "done"]));
    expect(String(fetchSpy.mock.calls[0][0])).toBe("/api/work-items/states?team_id=t1");
  });

  it("requests every state when unscoped", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse(["backlog"]));

    const { result } = renderHook(() => useWorkItemStates({}), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual(["backlog"]));
    expect(String(fetchSpy.mock.calls[0][0])).toBe("/api/work-items/states");
  });
});
