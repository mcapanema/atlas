import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test/fixtures";
import { useGuidance, useReflect, useRestoreGuidance } from "./personas";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const guidance = {
  persona: "agile_coach" as const,
  version: 2,
  guidance: "Focus on WIP limits.",
  created_at: "2026-07-12T00:00:00Z",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useGuidance", () => {
  it("fetches the persona's guidance history", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([guidance]));

    const { result } = renderHook(() => useGuidance("agile_coach"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([guidance]);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/personas/agile_coach/guidance",
      expect.anything(),
    );
  });
});

describe("useReflect", () => {
  it("posts a reflection request for the persona", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(guidance));

    const { result } = renderHook(() => useReflect("agile_coach"), { wrapper });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(String(url)).toBe("/api/personas/agile_coach/reflect");
    expect(init?.method).toBe("POST");
  });
});

describe("useRestoreGuidance", () => {
  it("posts a restore request for the given version", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(guidance));

    const { result } = renderHook(() => useRestoreGuidance("agile_coach"), { wrapper });
    result.current.mutate(1);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(String(url)).toBe("/api/personas/agile_coach/guidance/1/restore");
    expect(init?.method).toBe("POST");
  });
});
