import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { AUTH_KEY } from "./auth";
import { ApiError } from "./client";

function isUnauthorized(error: Error): boolean {
  return error instanceof ApiError && error.status === 401;
}

/**
 * The app's QueryClient. Any 401 means the session ended (expired, revoked,
 * or signed out in another tab): refetching the auth status flips the
 * AuthGate in App.tsx to the sign-in screen at the same URL.
 */
export function createQueryClient(): QueryClient {
  const onError = (error: Error) => {
    if (isUnauthorized(error)) void client.invalidateQueries({ queryKey: AUTH_KEY });
  };
  const client = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        // Dashboards refetch on every window focus with the default staleTime
        // of 0; 30s keeps tab-switching cheap while staying fresh enough for
        // delivery data.
        staleTime: 30_000,
        // A 401 won't heal on retry; the default 3 retries would hold the
        // sign-in screen back by several seconds.
        retry: (failureCount, error) => !isUnauthorized(error) && failureCount < 3,
      },
    },
  });
  return client;
}
