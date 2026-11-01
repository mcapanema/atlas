import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { authFixture } from "../test/fixtures";
import {
  AUTH_KEY,
  useAuthStatus,
  useChangePassword,
  useSetup,
  useSignIn,
  useSignOut,
} from "./auth";

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

describe("useSignOut with a mounted gate", () => {
  it("tells the components already watching the session", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    const { wrapper } = setup();
    // Separate roots, as the gate in App and the menu in the footer are.
    const gate = renderHook(() => useAuthStatus(), { wrapper });
    const menu = renderHook(() => useSignOut(), { wrapper });
    expect(gate.result.current.data?.user).not.toBeNull();

    await act(() => menu.result.current.mutateAsync());

    await waitFor(() => expect(gate.result.current.data?.user).toBeNull());
  });
});

describe("useSignIn", () => {
  it("drops queries left by an earlier user or an expired session", async () => {
    const user = authFixture().user;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(user), { status: 200 }),
    );
    const { client, wrapper } = setup();
    client.setQueryData(["teams"], [{ id: "t1" }]);
    client.setQueryData(AUTH_KEY, { setup_required: false, user: null });
    await client
      .fetchQuery({ queryKey: ["people"], queryFn: () => Promise.reject(new Error("401")) })
      .catch(() => {});
    expect(client.getQueryState(["people"])?.error).not.toBeNull();
    const { result } = renderHook(() => useSignIn(), { wrapper });

    await act(() => result.current.mutateAsync({ email: "a@b.co", password: "pw" }));

    expect(client.getQueryData(["teams"])).toBeUndefined();
    expect(client.getQueryState(["people"])).toBeUndefined();
    expect(client.getQueryData(AUTH_KEY)).toEqual({ setup_required: false, user });
  });
});

describe("useSetup", () => {
  it("returns to sign-in when another tab already made the account", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Atlas already has an account" }), { status: 409 }),
    );
    const { client, wrapper } = setup();
    client.setQueryData(AUTH_KEY, { setup_required: true, user: null });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useSetup(), { wrapper });

    await act(() =>
      result.current.mutateAsync({ email: "a@b.co", name: "A", password: "pw" }).catch(() => {}),
    );

    expect(invalidate).toHaveBeenCalledWith({ queryKey: AUTH_KEY });
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
