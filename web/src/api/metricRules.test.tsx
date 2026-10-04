import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRecomputeHistory } from "./metricRules";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useRecomputeHistory", () => {
  it("errors without fetching when there is no organization id", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const { result } = renderHook(() => useRecomputeHistory(undefined), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
