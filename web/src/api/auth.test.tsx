import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { authFixture } from "../test/fixtures";
import { AUTH_KEY, useChangePassword, useSignOut } from "./auth";

afterEach(() => {
  vi.restoreAllMocks();
});

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(AUTH_KEY, authFixture());
  client.setQueryData(["teams"], []);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

describe("useSignOut", () => {
  it("drops every cached query and leaves a signed-out status", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useSignOut(), { wrapper });

    await act(() => result.current.mutateAsync());

    expect(spy.mock.calls[0][0]).toBe("/api/auth/sign-out");
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
    expect(client.getQueryData(["teams"])).toBeUndefined();
    expect(client.getQueryData(AUTH_KEY)).toEqual({ setup_required: false, user: null });
  });
});

describe("useChangePassword", () => {
  it("puts the current and new password", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));
    const { wrapper } = setup();
    const { result } = renderHook(() => useChangePassword(), { wrapper });

    act(() => {
      result.current.mutate({
        current_password: "old-password-1",
        new_password: "new-password-12",
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy.mock.calls[0][0]).toBe("/api/auth/password");
    expect(spy.mock.calls[0][1]?.method).toBe("PUT");
    expect(spy.mock.calls[0][1]?.body).toBe(
      JSON.stringify({ current_password: "old-password-1", new_password: "new-password-12" }),
    );
  });
});
