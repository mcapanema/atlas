import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

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

// Sign-in and setup answer with the user, so the gate opens without a refetch.
function useSignedIn<V>(mutationFn: (values: V) => Promise<CurrentUser>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (user) => {
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
  return useSignedIn((values: { email: string; name: string; password: string }) =>
    postJson<CurrentUser>("/api/auth/setup", values),
  );
}

export function useSignOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postJson<undefined>("/api/auth/sign-out"),
    // Nothing the last user saw may outlive their session. The auth query
    // stays: clear() would detach the mounted gate, which then never hears
    // the signed-out status.
    onSuccess: () => {
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== AUTH_KEY[0] });
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
