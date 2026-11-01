import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { CurrentUser } from "./auth";
import { apiFetch } from "./client";

const USERS_KEY = ["users"] as const;

/** Admin only: every account, oldest first. */
export function useUsers() {
  return useQuery({
    queryKey: USERS_KEY,
    queryFn: () => apiFetch<CurrentUser[]>("/api/users"),
  });
}

function useUsersMutation<V>(mutationFn: (values: V) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_KEY }),
  });
}

export function useCreateUser() {
  return useUsersMutation(
    (values: { email: string; name: string; password: string; is_admin: boolean }) =>
      apiFetch<CurrentUser>("/api/users", { method: "POST", body: JSON.stringify(values) }),
  );
}

export function useResetPassword() {
  return useUsersMutation(({ id, new_password }: { id: string; new_password: string }) =>
    apiFetch<undefined>(`/api/users/${id}/password`, {
      method: "PUT",
      body: JSON.stringify({ new_password }),
    }),
  );
}

export function useDeleteUser() {
  return useUsersMutation((id: string) =>
    apiFetch<undefined>(`/api/users/${id}`, { method: "DELETE" }),
  );
}
