import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "./client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("apiFetch", () => {
  it("merges caller headers with the JSON content type", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await apiFetch("/api/things", { headers: { "X-Custom": "1" } });

    const sent = new Headers(spy.mock.calls[0][1]?.headers);
    expect(sent.get("Content-Type")).toBe("application/json");
    expect(sent.get("X-Custom")).toBe("1");
  });

  it("surfaces the FastAPI detail field from error responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Team not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiFetch("/api/things")).rejects.toThrow("Team not found");
  });

  it("falls back to the status code when the error body is not JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("boom", { status: 502 }));

    await expect(apiFetch("/api/things")).rejects.toThrow("Request failed: 502");
  });

  it("falls back to the status code when detail is not a string", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: [{ loc: ["body"], msg: "invalid" }] }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiFetch("/api/things")).rejects.toThrow("Request failed: 422");
  });
});
