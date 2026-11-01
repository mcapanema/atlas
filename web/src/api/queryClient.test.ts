import { MutationObserver } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { authFixture } from "../test/fixtures";
import { AUTH_KEY } from "./auth";
import { ApiError } from "./client";
import { createQueryClient } from "./queryClient";

function seededClient() {
  const client = createQueryClient();
  client.setQueryData(AUTH_KEY, authFixture());
  return client;
}

function failingQuery(client: ReturnType<typeof createQueryClient>, error: Error) {
  return client
    .fetchQuery({ queryKey: ["teams"], queryFn: () => Promise.reject(error), retry: false })
    .catch(() => undefined);
}

function failingMutation(client: ReturnType<typeof createQueryClient>, error: Error) {
  return new MutationObserver(client, { mutationFn: () => Promise.reject(error) })
    .mutate()
    .catch(() => undefined);
}

describe("createQueryClient", () => {
  it("keeps dashboards fresh for 30 seconds", () => {
    expect(createQueryClient().getDefaultOptions().queries?.staleTime).toBe(30_000);
  });

  it("refetches the auth status when a query gets 401", async () => {
    const client = seededClient();
    await failingQuery(client, new ApiError("Sign in to use Atlas", 401));
    expect(client.getQueryState(AUTH_KEY)?.isInvalidated).toBe(true);
  });

  it("ignores other query errors", async () => {
    const client = seededClient();
    await failingQuery(client, new ApiError("Internal Server Error", 500));
    expect(client.getQueryState(AUTH_KEY)?.isInvalidated).toBe(false);
  });

  it("refetches the auth status when a mutation gets 401", async () => {
    const client = seededClient();
    await failingMutation(client, new ApiError("Sign in to use Atlas", 401));
    expect(client.getQueryState(AUTH_KEY)?.isInvalidated).toBe(true);
  });

  it("ignores other mutation errors", async () => {
    const client = seededClient();
    await failingMutation(client, new Error("network down"));
    expect(client.getQueryState(AUTH_KEY)?.isInvalidated).toBe(false);
  });

  it("does not retry a 401, so the sign-in screen shows at once", () => {
    const retry = createQueryClient().getDefaultOptions().queries?.retry;
    expect(typeof retry).toBe("function");
    const shouldRetry = retry as (count: number, error: Error) => boolean;
    expect(shouldRetry(0, new ApiError("Sign in to use Atlas", 401))).toBe(false);
    expect(shouldRetry(0, new ApiError("Internal Server Error", 500))).toBe(true);
    expect(shouldRetry(3, new ApiError("Internal Server Error", 500))).toBe(false);
  });
});
