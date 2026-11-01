import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test/fixtures";
import { useRemoveCredentials, useSaveCredentials } from "./connectors";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderMutation<T>(hook: () => T) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const { result } = renderHook(hook, {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
  const invalidatedKeys = () => invalidate.mock.calls.map(([filters]) => filters?.queryKey);
  return { result, invalidatedKeys };
}

describe("credential mutations", () => {
  it("a GitHub save refetches the codebases: the owner may have changed", async () => {
    const { result, invalidatedKeys } = renderMutation(() => useSaveCredentials("github"));

    result.current.mutate({ token: "ghp_1", owner: "acme" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidatedKeys()).toContainEqual(["codebases"]);
  });

  it("a GitHub removal refetches the codebases", async () => {
    const { result, invalidatedKeys } = renderMutation(() => useRemoveCredentials("github"));

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidatedKeys()).toContainEqual(["codebases"]);
  });

  it("a Linear save leaves the codebases alone", async () => {
    const { result, invalidatedKeys } = renderMutation(() => useSaveCredentials("linear"));

    result.current.mutate({ api_key: "lin_1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidatedKeys()).toEqual([["connectors"], ["advisor", "status"]]);
  });
});
