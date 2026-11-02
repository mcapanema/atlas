import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiFetch } from "./client";

export interface CurrentUser {
  id: string;
  email: string;
  name: string;
  is_admin: boolean;
  created_at: string;
}

export interface AuthStatus {
  setup_required: boolean;
  user: CurrentUser | null;
}

export const AUTH_KEY = ["auth"] as const;

export function useAuthStatus() {
  return useQuery({
    queryKey: AUTH_KEY,
    queryFn: () => apiFetch<AuthStatus>("/api/auth/session"),
  });
}

function postJson<T>(path: string, body?: unknown) {
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
}

// Nothing the last user saw may outlive their session, and a mid-page
// expiry leaves 401 errors behind. The auth query stays: clear() would
// detach the mounted gate, which then never hears the new status.
function removeNonAuthQueries(queryClient: QueryClient) {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== AUTH_KEY[0] });
}

// Sign-in and setup answer with the user, so the gate opens without a refetch.
function useSignedIn<V>(
  mutationFn: (values: V) => Promise<CurrentUser>,
  onError?: (error: Error, queryClient: QueryClient) => void,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onError: (error) => onError?.(error, queryClient),
    onSuccess: (user) => {
      removeNonAuthQueries(queryClient);
      queryClient.setQueryData<AuthStatus>(AUTH_KEY, { setup_required: false, user });
    },
  });
}

export function useSignIn() {
  return useSignedIn((values: { email: string; password: string }) =>
    postJson<CurrentUser>("/api/auth/sign-in", values),
  );
}

export function useSetup() {
  return useSignedIn(
    (values: { email: string; name: string; password: string }) =>
      postJson<CurrentUser>("/api/auth/setup", values),
    // Another tab made the account first: show "Sign in" instead.
    (error, queryClient) => {
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: AUTH_KEY });
      }
    },
  );
}

export function useSignOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postJson<undefined>("/api/auth/sign-out"),
    onSuccess: () => {
      removeNonAuthQueries(queryClient);
      queryClient.setQueryData<AuthStatus>(AUTH_KEY, { setup_required: false, user: null });
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (values: { current_password: string; new_password: string }) =>
      apiFetch<undefined>("/api/auth/password", { method: "PUT", body: JSON.stringify(values) }),
  });
}
